from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from core.providers.base import (
    ChatMessage,
    LLMCallOptions,
    LLMCompletionResult,
    LLMProvider,
    TokenUsage,
)
from core.providers.registry import build_provider
from core.providers.stream_types import StreamTextDelta, StreamUsagePart
from core.utils.usage_logger import approximate_usage_from_text, log_llm_usage

log = logging.getLogger(__name__)


@dataclass
class FallbackStep:
    provider_id: str
    model: str
    api_key_env: str | None = None


class LLMAllProvidersFailed(RuntimeError):
    def __init__(self, errors: list[tuple[str, str, Exception]]) -> None:
        self.errors = errors
        parts = [f"{prov}/{model}: {exc!s}" for prov, model, exc in errors]
        super().__init__("All LLM fallbacks failed: " + " | ".join(parts))


def _prompt_digest(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{m.role}:{m.content}" for m in messages)


class FallbackLLMClient:
    """
    Tries primary provider/model, then optional fallback chain.
    Builds provider instances per attempt so fresh API keys are read from env.
    Records token usage + estimated cost per successful call.
    """

    def __init__(
        self,
        steps: list[FallbackStep],
        env_getter: Callable[[str], str | None] | None = None,
        agent_type: str | None = None,
    ) -> None:
        if not steps:
            raise ValueError("FallbackLLMClient requires at least one step")
        self._steps = steps
        self._env_getter = env_getter
        self._agent_type = agent_type or "unknown"

    def _instance_for(self, step: FallbackStep) -> tuple[LLMProvider, str] | None:
        from core.utils.credentials import resolve_api_key_for_provider

        key = resolve_api_key_for_provider(
            step.provider_id,
            api_key_env=step.api_key_env,
            env_getter=self._env_getter,
        )
        if not key:
            log.warning(
                "Skipping %s/%s: missing API key (env %s)",
                step.provider_id,
                step.model,
                step.api_key_env or "(default)",
            )
            return None
        prov = build_provider(step.provider_id, key)
        return prov, step.model

    def _emit_usage(
        self,
        *,
        provider_id: str,
        model: str,
        usage: TokenUsage,
        streaming: bool,
    ) -> None:
        log_llm_usage(
            agent_type=self._agent_type,
            provider=provider_id,
            model=model,
            usage=usage,
            streaming=streaming,
        )

    def _usage_for_completion(
        self,
        messages: list[ChatMessage],
        result: LLMCompletionResult,
        provider_id: str,
        model: str,
    ) -> None:
        if result.usage:
            self._emit_usage(
                provider_id=provider_id,
                model=model,
                usage=result.usage,
                streaming=False,
            )
        elif result.text:
            approx = approximate_usage_from_text(
                _prompt_digest(messages),
                result.text,
            )
            self._emit_usage(
                provider_id=provider_id,
                model=model,
                usage=approx,
                streaming=False,
            )

    def complete(
        self,
        messages: list[ChatMessage],
        options: LLMCallOptions | None = None,
    ) -> LLMCompletionResult:
        errors: list[tuple[str, str, Exception]] = []
        opts = options or LLMCallOptions()
        for step in self._steps:
            built = self._instance_for(step)
            if not built:
                errors.append(
                    (step.provider_id, step.model, RuntimeError("Missing API key"))
                )
                continue
            provider, model = built
            try:
                result = provider.complete(messages, model, opts)
                self._usage_for_completion(messages, result, step.provider_id, model)
                return result
            except Exception as exc:  # noqa: BLE001 — aggregate for fallback
                log.warning(
                    "LLM failure %s/%s: %s",
                    step.provider_id,
                    step.model,
                    exc,
                    exc_info=log.isEnabledFor(logging.DEBUG),
                )
                errors.append((step.provider_id, step.model, exc))
        raise LLMAllProvidersFailed(errors)

    async def acomplete_stream_parts(
        self,
        messages: list[ChatMessage],
        options: LLMCallOptions | None = None,
    ) -> AsyncIterator[StreamTextDelta | StreamUsagePart]:
        opts = options or LLMCallOptions()
        errors: list[tuple[str, str, Exception]] = []
        for step in self._steps:
            built = self._instance_for(step)
            if not built:
                errors.append(
                    (step.provider_id, step.model, RuntimeError("Missing API key"))
                )
                continue
            provider, model = built
            if not getattr(provider, "supports_streaming", False):
                errors.append(
                    (
                        step.provider_id,
                        step.model,
                        RuntimeError("Provider does not support streaming"),
                    )
                )
                continue
            buffer: list[str] = []
            saw_usage = False
            try:
                async for part in provider.acomplete_stream_parts(messages, model, opts):
                    if isinstance(part, StreamTextDelta):
                        buffer.append(part.text)
                        yield part
                    elif isinstance(part, StreamUsagePart):
                        saw_usage = True
                        self._emit_usage(
                            provider_id=step.provider_id,
                            model=model,
                            usage=TokenUsage(
                                input_tokens=part.input_tokens,
                                output_tokens=part.output_tokens,
                                total_tokens=part.total_tokens,
                            ),
                            streaming=True,
                        )
                        yield part
                if not saw_usage and buffer:
                    full = "".join(buffer)
                    approx = approximate_usage_from_text(
                        _prompt_digest(messages),
                        full,
                    )
                    self._emit_usage(
                        provider_id=step.provider_id,
                        model=model,
                        usage=approx,
                        streaming=True,
                    )
                    yield StreamUsagePart(
                        input_tokens=approx.input_tokens,
                        output_tokens=approx.output_tokens,
                        total_tokens=approx.total_tokens,
                    )
                return
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "LLM stream failure %s/%s: %s",
                    step.provider_id,
                    step.model,
                    exc,
                )
                errors.append((step.provider_id, step.model, exc))
        raise LLMAllProvidersFailed(errors)

    async def acomplete_stream(
        self,
        messages: list[ChatMessage],
        options: LLMCallOptions | None = None,
    ) -> AsyncIterator[str]:
        async for part in self.acomplete_stream_parts(messages, options):
            if isinstance(part, StreamTextDelta):
                yield part.text

    async def acomplete_text(
        self,
        messages: list[ChatMessage],
        options: LLMCallOptions | None = None,
    ) -> LLMCompletionResult:
        """Non-streaming async wrapper (runs sync complete in executor)."""

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.complete(messages, options)
        )
