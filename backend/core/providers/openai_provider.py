from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI, OpenAI

from core.providers.base import (
    ChatMessage,
    LLMCallOptions,
    LLMCompletionResult,
    LLMProvider,
    TokenUsage,
)
from core.providers.stream_types import StreamTextDelta, StreamUsagePart


def _messages_to_openai(messages: list[ChatMessage]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        if m.role == "system":
            out.append({"role": "system", "content": m.content})
        elif m.role == "user":
            out.append({"role": "user", "content": m.content})
        else:
            out.append({"role": "assistant", "content": m.content})
    return out


def _usage_from_openai(u: Any) -> TokenUsage | None:
    if u is None:
        return None
    pt = getattr(u, "prompt_tokens", None)
    ct = getattr(u, "completion_tokens", None)
    tt = getattr(u, "total_tokens", None)
    if pt is None and ct is None:
        return None
    return TokenUsage(
        input_tokens=int(pt or 0),
        output_tokens=int(ct or 0),
        total_tokens=int(tt) if tt is not None else None,
    )


class OpenAIProvider(LLMProvider):
    name = "openai"
    supports_streaming = True

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._sync = OpenAI(api_key=api_key, base_url=base_url)
        self._async = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ) -> LLMCompletionResult:
        opts = options or LLMCallOptions()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _messages_to_openai(messages),
        }
        if opts.temperature is not None:
            kwargs["temperature"] = opts.temperature
        if opts.max_tokens is not None:
            kwargs["max_tokens"] = opts.max_tokens
        if opts.timeout_seconds is not None:
            kwargs["timeout"] = opts.timeout_seconds

        resp = self._sync.chat.completions.create(**kwargs)
        text = (resp.choices[0].message.content or "").strip()
        usage = _usage_from_openai(getattr(resp, "usage", None))
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
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _messages_to_openai(messages),
            "stream": True,
        }
        if opts.temperature is not None:
            kwargs["temperature"] = opts.temperature
        if opts.max_tokens is not None:
            kwargs["max_tokens"] = opts.max_tokens
        if opts.timeout_seconds is not None:
            kwargs["timeout"] = opts.timeout_seconds

        try:
            stream = await self._async.chat.completions.create(
                **kwargs,
                stream_options={"include_usage": True},
            )
        except TypeError:
            stream = await self._async.chat.completions.create(**kwargs)
        last_usage: TokenUsage | None = None
        async for event in stream:
            ch0 = event.choices[0] if event.choices else None
            if ch0 and ch0.delta and ch0.delta.content:
                yield StreamTextDelta(ch0.delta.content)
            u = _usage_from_openai(getattr(event, "usage", None))
            if u:
                last_usage = u
        if last_usage:
            yield StreamUsagePart(
                input_tokens=last_usage.input_tokens,
                output_tokens=last_usage.output_tokens,
                total_tokens=last_usage.total_tokens,
            )
