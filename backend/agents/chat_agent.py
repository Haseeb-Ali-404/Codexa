from __future__ import annotations

from typing import Any

from core.factory.agent_factory import create_agent


class ChatAgent:
    def __init__(self, **kwargs: Any) -> None:
        self._inner = create_agent("chat", **kwargs)

    @staticmethod
    def convert_messages_to_text(messages: list) -> str:
        from core.agents.chat_agent import ChatAgent as CoreChatAgent

        return CoreChatAgent.convert_messages_to_text(messages)

    def respond(self, project_id: str, user_message: str) -> str:
        return self._inner.respond(project_id, user_message)

    async def stream_respond(self, project_id: str, user_message: str):
        async for piece in self._inner.stream_respond(project_id, user_message):
            yield piece
