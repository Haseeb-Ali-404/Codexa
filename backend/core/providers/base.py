from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from collections.abc import AsyncIterator
from typing import Any, Literal

from core.providers.stream_types import StreamPart, StreamTextDelta, StreamUsagePart

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int | None = None

    def normalized_total(self) -> int:
        if self.total_tokens is not None:
            return self.total_tokens
        return self.input_tokens + self.output_tokens


@dataclass
class LLMCompletionResult:
    """Normalized completion output (provider-agnostic)."""

    text: str
    raw: Any | None = None
    provider_name: str = ""
    model: str = ""
    usage: TokenUsage | None = None


@dataclass
class LLMCallOptions:
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = 120.0
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Unified interface for text completions (chat-style messages in, text out)."""

    name: str
    supports_streaming: bool = False

    @abstractmethod
    def complete(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ) -> LLMCompletionResult:
        pass

    async def acomplete_stream_parts(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ) -> AsyncIterator[StreamPart]:
        """Text deltas and a final usage part when available."""
        opts = options or LLMCallOptions()
        result = self.complete(messages, model, opts)
        if result.text:
            yield StreamTextDelta(result.text)
        if result.usage:
            yield StreamUsagePart(
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                total_tokens=result.usage.total_tokens,
            )

    async def acomplete_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        options: LLMCallOptions | None = None,
    ) -> AsyncIterator[str]:
        async for part in self.acomplete_stream_parts(messages, model, options):
            if isinstance(part, StreamTextDelta):
                yield part.text
