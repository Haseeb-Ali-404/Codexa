from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from core.providers.base import (
    ChatMessage,
    LLMCallOptions,
    LLMCompletionResult,
    LLMProvider,
    TokenUsage,
)
from core.providers.stream_types import StreamTextDelta, StreamUsagePart


def _messages_to_contents(messages: list[ChatMessage]) -> list[types.Content]:
    """Convert ChatMessage list to Gemini Content objects with proper role mapping."""
    contents = []
    for m in messages:
        role = "user" if m.role in ("user", "system") else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=m.content)])
        )
    return contents


def _build_config(opts: LLMCallOptions) -> types.GenerateContentConfig | None:
    kwargs: dict[str, Any] = {}
    if opts.temperature is not None:
        kwargs["temperature"] = opts.temperature
    if opts.max_tokens is not None:
        # Gemini 2.5 Pro max output is 65536 — cap silently
        kwargs["max_output_tokens"] = min(opts.max_tokens, 65536)
    # Control thinking budget: 0 = no thinking (max code output), >0 = reasoning budget
    thinking_budget = getattr(opts, "thinking_budget", None)
    if thinking_budget is not None:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    return types.GenerateContentConfig(**kwargs) if kwargs else None


def _usage_from_gemini(meta: Any) -> TokenUsage | None:
    if meta is None:
        return None
    pt = getattr(meta, "prompt_token_count", None)
    ct = getattr(meta, "candidates_token_count", None)
    tt = getattr(meta, "total_token_count", None)
    if pt is None and ct is None and tt is None:
        return None
    return TokenUsage(
        input_tokens=int(pt or 0),
        output_tokens=int(ct or 0),
        total_tokens=int(tt) if tt is not None else None,
    )


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_streaming = True

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    def complete(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ) -> LLMCompletionResult:
        opts = options or LLMCallOptions()
        contents = _messages_to_contents(messages)
        config = _build_config(opts)
        resp = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        text = (getattr(resp, "text", None) or "").strip()
        if not text:
            text = self._text_from_candidates(resp)
        usage = _usage_from_gemini(getattr(resp, "usage_metadata", None))
        if usage:
            print(f"[Gemini] tokens: input={usage.input_tokens} output={usage.output_tokens}")
        return LLMCompletionResult(
            text=text,
            raw=resp,
            provider_name=self.name,
            model=model,
            usage=usage,
        )

    @staticmethod
    def _text_from_candidates(resp: Any) -> str:
        candidates = getattr(resp, "candidates", []) or []
        if not candidates:
            return ""
        content = getattr(candidates[0], "content", None)
        if not content:
            return ""
        parts = getattr(content, "parts", []) or []
        return "".join(
            getattr(p, "text", "") for p in parts if getattr(p, "text", None)
        ).strip()

    async def acomplete_stream_parts(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ):
        opts = options or LLMCallOptions()
        contents = _messages_to_contents(messages)
        config = _build_config(opts)

        stream = await self._client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        )
        last_meta: Any = None
        async for chunk in stream:
            piece = getattr(chunk, "text", None) or ""
            if piece:
                yield StreamTextDelta(piece)
            meta = getattr(chunk, "usage_metadata", None)
            if meta is not None:
                last_meta = meta
        usage = _usage_from_gemini(last_meta)
        if usage:
            print(f"[Gemini-stream] tokens: input={usage.input_tokens} output={usage.output_tokens}")
            yield StreamUsagePart(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
