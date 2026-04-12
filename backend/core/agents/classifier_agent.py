import json

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


class ClassifierAgent:
    CLASSIFIER_PROMPT = """
You are an intent classifier for CODEXA (AI coding IDE).

Context:
{context_note}

Classify ONLY the user's intent.

Valid types:
- "project"        → User wants to CREATE / BUILD / GENERATE a new app or site from scratch (greenfield).
- "edit"           → User wants to CHANGE / FIX / ADD / UPDATE / REMOVE something in an EXISTING codebase (only meaningful when a project already exists).
- "conversation"   → Questions, explanations, chat, or requests that do not require code edits (or no project exists yet and they are not asking to scaffold a full app).

Examples:
- "Build a todo app" → project
- "Add dark mode" (project exists) → edit
- "Fix the login bug" (project exists) → edit
- "What does useEffect do?" → conversation
- "Change the button color to blue" (project exists) → edit

Your response MUST be ONLY valid JSON.
NO markdown.
NO comments.
NO text outside JSON.

JSON FORMAT:
{
  "type": "<project|edit|conversation>",
  "reason": "short"
}

User message:
{message}
"""

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    def classify(self, message: str, *, has_project: bool = False):
        context_note = (
            "A generated project (files) is already linked to this chat."
            if has_project
            else "No generated project is linked to this chat yet."
        )
        prompt = (
            self.CLASSIFIER_PROMPT.replace("{context_note}", context_note).replace(
                "{message}", message
            )
        )
        messages = [ChatMessage(role="user", content=prompt)]

        try:
            result = self._llm.complete(messages, self._opts)
            raw = result.text.strip()
            print("Classifier response:", raw)
        except Exception as e:
            print("❌ Classifier error:", e)
            return {
                "type": "conversation",
                "reason": "model_call_failed",
            }

        clean = (
            raw.replace("```json", "")
            .replace("```", "")
            .strip()
        )

        try:
            return json.loads(clean)
        except Exception as e:
            print("❌ JSON decode failed:", clean, e)
            return {
                "type": "conversation",
                "reason": "invalid_json",
            }

    def classify_for_project(
        self,
        message: str,
        chat_id: str | None,
        *,
        has_project: bool = False,
    ):
        intent = self.classify(message, has_project=has_project)
        print(intent)
        t = intent.get("type")
        if t == "edit" and not has_project:
            return {
                "type": "conversation",
                "reason": "edit_intent_without_project",
            }
        if t not in ("project", "edit", "conversation"):
            intent["type"] = "conversation"
        return intent
