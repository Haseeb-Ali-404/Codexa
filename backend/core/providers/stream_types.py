from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class StreamTextDelta:
    text: str


@dataclass
class StreamUsagePart:
    """Emitted once at end of a stream when the provider exposes usage."""

    input_tokens: int
    output_tokens: int
    total_tokens: int | None = None


StreamPart = Union[StreamTextDelta, StreamUsagePart]
