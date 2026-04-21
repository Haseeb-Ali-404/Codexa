from core.memory.memory_store import build_chat_messages_for_llm
from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient, LLMAllProvidersFailed
from utils.database_models_util import save_message


CHAT_SYSTEM_PROMPT = """You are CODEXA, an expert AI coding assistant inside an IDE.

You have three sources of context:
  1. The full prior conversation in this chat (as chat messages below). Resolve pronouns
     and follow-ups ("that", "the navbar", "make it smaller") from this history.
  2. An optional PROJECT CONTEXT block describing the user's generated project
     (title, file manifest, last edits). Use it to give grounded answers about
     their code — do NOT invent files or APIs that aren't in the manifest.
  3. The user's latest message.

Style:
  - Be concise, accurate, and actionable.
  - Use markdown for code snippets when helpful.
  - If the user asks you to make a change to their code, acknowledge it briefly and
     mention that it will be applied as an edit (the system will handle the file update).
  - If you don't know something, say so — don't fabricate.
"""


class ChatAgent:
    """
    Conversational agent: multi-turn history (trimmed) + provider-agnostic LLM.
    """

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    @staticmethod
    def convert_messages_to_text(messages: list) -> str:
        lines = []
        for m in messages:
            role = "User" if m["role"] == "user" else "Assistant"
            lines.append(f"{role}: {m['content']}")
        return "\n".join(lines)

    def _messages_for_llm(
        self,
        chat_id: str,
        project_context: str | None = None,
    ) -> list[ChatMessage]:
        system_prompt = CHAT_SYSTEM_PROMPT
        if project_context and project_context.strip():
            system_prompt = (
                CHAT_SYSTEM_PROMPT
                + "\n\n## PROJECT CONTEXT\n"
                + project_context.strip()
            )
        return build_chat_messages_for_llm(
            chat_id,
            system_prompt=system_prompt,
            max_messages=30,
        )

    def respond(
        self,
        project_id: str,
        user_message: str,
        project_context: str | None = None,
    ) -> str:
        del user_message  # latest user turn is already persisted in DB
        messages = self._messages_for_llm(project_id, project_context=project_context)
        try:
            result = self._llm.complete(messages, self._opts)
        except LLMAllProvidersFailed as e:
            msg = "Sorry, the AI service is temporarily unavailable. Please try again."
            print("Chat LLM failure:", e)
            return msg

        reply = result.text.strip()
        print("Chat reply:", reply)
        save_message(project_id, "assistant", reply, "chat")

        return reply

    async def stream_respond(
        self,
        project_id: str,
        user_message: str,
        project_context: str | None = None,
    ):
        del user_message
        messages = self._messages_for_llm(project_id, project_context=project_context)
        pieces: list[str] = []

        try:
            async for piece in self._llm.acomplete_stream(messages, self._opts):
                if piece:
                    pieces.append(piece)
                    yield piece
        except LLMAllProvidersFailed:
            err = "Sorry, the AI service is temporarily unavailable. Please try again."
            yield err
            pieces.append(err)

        reply = "".join(pieces).strip()
        if reply:
            save_message(project_id, "assistant", reply, "chat")
