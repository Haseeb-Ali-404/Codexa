"""
Chat memory: persist and retrieve messages per chat_id with trimming for LLM context.
Backed by MongoDB (messages_col) via database_models_util.
"""

from __future__ import annotations

from core.providers.base import ChatMessage
from utils.database_models_util import get_chat_messages, save_message as db_save_message
from utils.database_util import messages_col

MAX_MESSAGES_DEFAULT = 20
MAX_CONTEXT_CHARS = 32000
MAX_SINGLE_MESSAGE_CHARS = 16000
OMIT_AGENT_THRESHOLD = 1200


def save_message(chat_id: str, role: str, content: str, agent: str | None = None) -> bool:
    return bool(db_save_message(chat_id, role, content, agent))


def get_messages(chat_id: str) -> list[dict]:
    """All messages as simple dicts (role, content, optional agent)."""
    raw = get_chat_messages(chat_id)
    return [
        {
            "role": m.get("role") or "user",
            "content": m.get("content") or "",
            "agent": m.get("agent"),
        }
        for m in raw
    ]


def clear_chat(chat_id: str) -> bool:
    messages_col.delete_many({"chat_id": chat_id})
    return True


def sanitize_message_for_llm(msg: dict) -> dict[str, str]:
    role = msg.get("role") or "user"
    content = msg.get("content") or ""
    agent = msg.get("agent")

    if agent in ("pipeline", "developer", "debugger", "planner") and len(content) > OMIT_AGENT_THRESHOLD:
        content = f"[{agent} output omitted ({len(content)} characters)]"
    elif len(content) > MAX_SINGLE_MESSAGE_CHARS:
        content = content[:MAX_SINGLE_MESSAGE_CHARS] + "\n...[truncated]"

    if role not in ("user", "assistant"):
        role = "user"
    return {"role": role, "content": content}


def get_trimmed_messages(
    chat_id: str,
    *,
    max_messages: int = MAX_MESSAGES_DEFAULT,
    max_context_chars: int = MAX_CONTEXT_CHARS,
) -> list[dict[str, str]]:
    raw = get_chat_messages(chat_id)
    sliced = raw[-max_messages:] if len(raw) > max_messages else raw
    out: list[dict[str, str]] = []
    for m in sliced:
        out.append(
            sanitize_message_for_llm(
                {
                    "role": m.get("role"),
                    "content": m.get("content"),
                    "agent": m.get("agent"),
                }
            )
        )
    total = sum(len(m["content"]) for m in out) + 50 * len(out)
    while total > max_context_chars and len(out) > 2:
        out.pop(0)
        total = sum(len(m["content"]) for m in out) + 50 * len(out)
    return out


def merge_consecutive_same_role(turns: list[dict[str, str]]) -> list[dict[str, str]]:
    if not turns:
        return []
    merged = [dict(turns[0])]
    for m in turns[1:]:
        if m["role"] == merged[-1]["role"]:
            merged[-1]["content"] = merged[-1]["content"] + "\n\n" + m["content"]
        else:
            merged.append(dict(m))
    return merged


def build_chat_messages_for_llm(
    chat_id: str,
    *,
    system_prompt: str | None = None,
    max_messages: int = MAX_MESSAGES_DEFAULT,
) -> list[ChatMessage]:
    """
    Multi-turn history for providers: optional system + user/assistant alternating (merged where needed).
    """
    trimmed = get_trimmed_messages(chat_id, max_messages=max_messages)
    merged = merge_consecutive_same_role(trimmed)
    out: list[ChatMessage] = []
    if system_prompt:
        out.append(ChatMessage(role="system", content=system_prompt))
    for m in merged:
        out.append(ChatMessage(role=m["role"], content=m["content"]))  # type: ignore[arg-type]
    return out


def summarize_old_messages_stub(_chat_id: str) -> str | None:
    """Hook for future summarization of aged history; returns None to skip."""
    return None
