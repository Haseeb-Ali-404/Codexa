import json
import re

from core.memory.memory_store import build_chat_messages_for_llm
from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient, LLMAllProvidersFailed
from utils.database_models_util import save_message
from utils.json_parser import parse_json_block


def _chat_agent_log(message: str) -> None:
    print(f"[ChatAgent] {message}", flush=True)


CHAT_SYSTEM_PROMPT = """You are CODEXA, an expert AI coding assistant inside an IDE.

You have three sources of context:
  1. The full prior conversation in this chat (as chat messages below). Resolve pronouns
     and follow-ups ("that", "the navbar", "make it smaller") from this history.
  2. An optional PROJECT CONTEXT block describing the user's generated project
     (title, file manifest, last edits). Use it to give grounded answers about
     their code and do not invent files or APIs that are not in the manifest.
  3. The user's latest message.

Return STRICT JSON only in this format:
{
  "type": "conversation",
  "content": [
    { "type": "text", "value": "..." },
    { "type": "code", "content": "...", "language": "javascript" }
  ]
}

Rules:
  - Maintain the original order of explanation and code.
  - Always use the outer content array, even for one item.
  - Code items must include a language.
  - Use short, clear text blocks.
  - Include code blocks only when helpful.
  - If the user asks to change their project code, mention the edit succinctly in text only; the edit system handles file updates separately.
  - Do not wrap the JSON in markdown fences.
"""

_CODE_FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_+#.-]*)\s*\n(?P<code>.*?)```",
    re.DOTALL,
)


def _normalize_language(language: str | None) -> str:
    value = (language or "").strip().lower()
    return value or "text"


def _strip_text_block(text: str) -> str:
    return (text or "").strip()


def _conversation_payload_from_text(raw: str) -> dict:
    text = raw or ""
    items: list[dict] = []
    cursor = 0

    for match in _CODE_FENCE_RE.finditer(text):
        before = _strip_text_block(text[cursor : match.start()])
        if before:
            items.append({"type": "text", "value": before})

        code = (match.group("code") or "").rstrip()
        if code.strip():
            items.append(
                {
                    "type": "code",
                    "content": code,
                    "language": _normalize_language(match.group("lang")),
                }
            )
        cursor = match.end()

    tail = _strip_text_block(text[cursor:])
    if tail:
        items.append({"type": "text", "value": tail})

    if not items:
        cleaned = _strip_text_block(text)
        items = [{"type": "text", "value": cleaned or "I could not produce a response."}]

    return {"type": "conversation", "content": items}


def _normalize_conversation_payload(raw: str) -> dict:
    parsed = parse_json_block(raw, default=None)
    if isinstance(parsed, dict) and str(parsed.get("type") or "").strip().lower() == "conversation":
        normalized_items: list[dict] = []
        for item in parsed.get("content") or []:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "text":
                value = _strip_text_block(str(item.get("value") or ""))
                if value:
                    normalized_items.append({"type": "text", "value": value})
            elif item_type == "code":
                content = str(item.get("content") or "").rstrip()
                if content.strip():
                    normalized_items.append(
                        {
                            "type": "code",
                            "content": content,
                            "language": _normalize_language(str(item.get("language") or "")),
                        }
                    )
        if normalized_items:
            return {"type": "conversation", "content": normalized_items}

    return _conversation_payload_from_text(raw)


def _serialize_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _payload_to_stream_text(payload: dict) -> str:
    parts: list[str] = []
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if item_type == "text":
            value = _strip_text_block(str(item.get("value") or ""))
            if value:
                parts.append(value)
        elif item_type == "code":
            content = str(item.get("content") or "").rstrip()
            if content.strip():
                language = _normalize_language(str(item.get("language") or ""))
                parts.append(f"```{language}\n{content}\n```")
    return "\n\n".join(parts).strip()


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

    def _save_payload(self, chat_id: str, payload: dict) -> str:
        reply = _serialize_payload(payload)
        save_message(chat_id, "assistant", reply, "chat")
        return reply

    def payload_to_stream_text(self, payload: dict) -> str:
        return _payload_to_stream_text(payload)

    def respond(
        self,
        project_id: str,
        user_message: str,
        project_context: str | None = None,
    ) -> str:
        _chat_agent_log(f"respond start chat_id={project_id}")
        del user_message
        messages = self._messages_for_llm(project_id, project_context=project_context)
        try:
            result = self._llm.complete(messages, self._opts)
            payload = _normalize_conversation_payload((result.text or "").strip())
        except LLMAllProvidersFailed as e:
            _chat_agent_log(f"llm failure chat_id={project_id} err={e}")
            payload = {
                "type": "conversation",
                "content": [
                    {
                        "type": "text",
                        "value": "Sorry, the AI service is temporarily unavailable. Please try again.",
                    }
                ],
            }

        reply = self._save_payload(project_id, payload)
        _chat_agent_log(
            f"respond done chat_id={project_id} blocks={len(payload.get('content') or [])}"
        )
        return reply

    async def generate_structured_payload(
        self,
        project_id: str,
        user_message: str,
        project_context: str | None = None,
    ) -> dict:
        _chat_agent_log(f"generate start chat_id={project_id}")
        del user_message
        messages = self._messages_for_llm(project_id, project_context=project_context)

        try:
            result = await self._llm.acomplete_text(messages, self._opts)
            payload = _normalize_conversation_payload((result.text or "").strip())
        except LLMAllProvidersFailed:
            _chat_agent_log(f"async llm failure chat_id={project_id}")
            payload = {
                "type": "conversation",
                "content": [
                    {
                        "type": "text",
                        "value": "Sorry, the AI service is temporarily unavailable. Please try again.",
                    }
                ],
            }

        self._save_payload(project_id, payload)
        _chat_agent_log(
            f"generate done chat_id={project_id} blocks={len(payload.get('content') or [])}"
        )
        return payload

    async def stream_respond(
        self,
        project_id: str,
        user_message: str,
        project_context: str | None = None,
    ):
        payload = await self.generate_structured_payload(
            project_id,
            user_message,
            project_context=project_context,
        )
        yield _serialize_payload(payload)
