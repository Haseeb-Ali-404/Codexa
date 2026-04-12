from __future__ import annotations

from typing import Any

import anthropic

from core.providers.base import (
    ChatMessage,
    LLMCallOptions,
    LLMCompletionResult,
    LLMProvider,
    TokenUsage,
)
from core.providers.stream_types import StreamTextDelta, StreamUsagePart


def _split_system_user(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, str]]]:
    system_parts: list[str] = []
    api_messages: list[dict[str, str]] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        elif m.role == "user":
            api_messages.append({"role": "user", "content": m.content})
        else:
            api_messages.append({"role": "assistant", "content": m.content})
    system = "\n\n".join(system_parts) if system_parts else None
    return system, api_messages


def _usage_from_anthropic(u: Any) -> TokenUsage | None:
    if u is None:
        return None
    inp = getattr(u, "input_tokens", None)
    out = getattr(u, "output_tokens", None)
    if inp is None and out is None:
        return None
    return TokenUsage(
        input_tokens=int(inp or 0),
        output_tokens=int(out or 0),
        total_tokens=None,
    )


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    supports_streaming = True

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._async = anthropic.AsyncAnthropic(api_key=api_key)

    def complete(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ) -> LLMCompletionResult:
        opts = options or LLMCallOptions()
        system, api_messages = _split_system_user(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": opts.max_tokens or 4096,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if opts.temperature is not None:
            kwargs["temperature"] = opts.temperature
        if opts.timeout_seconds is not None:
            kwargs["timeout"] = opts.timeout_seconds

        resp = self._client.messages.create(**kwargs)
        parts = []
        for block in resp.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        text = "".join(parts).strip()
        usage = _usage_from_anthropic(getattr(resp, "usage", None))
        return LLMCompletionResult(
            text=text,
            raw=resp,
            provider_name=self.name,
            model=model,
            usage=usage,
        )

    async def acomplete_stream_parts(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ):
        opts = options or LLMCallOptions()
        system, api_messages = _split_system_user(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": opts.max_tokens or 4096,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if opts.temperature is not None:
            kwargs["temperature"] = opts.temperature
        if opts.timeout_seconds is not None:
            kwargs["timeout"] = opts.timeout_seconds

        async with self._async.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    yield StreamTextDelta(text)
            try:
                msg = await stream.get_final_message()
            except Exception:
                msg = None
            if msg is not None:
                usage = _usage_from_anthropic(getattr(msg, "usage", None))
                if usage:
                    yield StreamUsagePart(
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        total_tokens=usage.total_tokens,
                    )
