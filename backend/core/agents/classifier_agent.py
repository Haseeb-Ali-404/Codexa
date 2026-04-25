import json
import re

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


class ClassifierAgent:
    CLASSIFIER_PROMPT = """
You are an intent classifier for CODEXA (AI coding IDE).

Context:
{context_note}

Classify ONLY the user's intent. Pick exactly one type.

DECISION RULES (apply in order):

1. If a project is already linked to this chat AND the user wants ANY kind of change to the code, styling, text, layout, behavior, feature, or content → "edit".
   Signals that mean "edit" when a project exists: "change", "update", "modify", "edit", "add", "remove", "delete", "fix", "rename", "replace", "make it", "make the", "style", "color", "bigger", "smaller", "move", "also include", "use", "put", "show", "hide", "can you", "please", "navbar", "header", "footer", "button", "page", "component", a color name, a file/component name, any description of what the UI/logic should do.

2. If NO project is linked yet AND the user is asking to CREATE/BUILD/GENERATE a full app, site, dashboard, or tool from scratch → "project".
   Signals: "build", "create", "generate", "make me", "I want a", "design a", an idea description ("a SaaS for X", "a landing page for Y").

3. Otherwise → "conversation" (questions, explanations, general chat, greetings, follow-up questions about the code, planning discussions).

IMPORTANT:
- When a project exists, DEFAULT to "edit" for anything actionable. Only choose "conversation" if the user is asking a pure question ("what does this do?", "why did you use Zustand?", "explain the auth flow").
- Never classify as "project" when a project already exists — the user cannot scaffold a second greenfield project into the same chat.
- Very short messages like "make the navbar blue", "add dark mode", "change title to X" are ALWAYS "edit" if a project exists.

Examples:
- "Build a todo app" (no project) → project
- "A SaaS for dog grooming" (no project) → project
- "Add dark mode" (project exists) → edit
- "change the navbar color to blue" (project exists) → edit
- "rename the app to Luminos" (project exists) → edit
- "also add a pricing page" (project exists) → edit
- "make the hero bigger" (project exists) → edit
- "fix the login bug" (project exists) → edit
- "what does useEffect do?" → conversation
- "why did you use Zustand?" (project exists) → conversation
- "thanks" / "ok" → conversation

Your response MUST be ONLY valid JSON. NO markdown, no comments, no text outside JSON.

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

    _TYPE_RE = re.compile(
        r'"type"\s*:\s*"?(project|edit|conversation)?',
        re.IGNORECASE,
    )

    def _heuristic_intent(self, message: str, *, has_project: bool = False) -> dict:
        low = (message or "").strip().lower()
        if not low:
            return {
                "type": "conversation",
                "reason": "empty_message",
            }

        if self._is_strong_project_signal(low):
            if has_project:
                return {
                    "type": "edit",
                    "reason": "project_prompt_in_existing_project_chat",
                }
            return {
                "type": "project",
                "reason": "keyword_project_signal",
            }

        return {
            "type": "conversation",
            "reason": "heuristic_conversation_fallback",
        }

    def _extract_partial_type(self, raw: str) -> str | None:
        if not raw:
            return None
        match = self._TYPE_RE.search(raw)
        if not match:
            return None
        intent_type = (match.group(1) or "").strip().lower()
        return intent_type or None

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
            print("[Classifier] Response:", raw)
        except Exception as e:
            print("[Classifier] Error:", e)
            return {
                "type": "conversation",
                "reason": "model_call_failed",
            }

        # Clean markdown wrappers and fix common issues
        clean = raw
        # Remove markdown code blocks
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0]
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0]
        else:
            clean = raw.strip()
        
        clean = clean.strip()

        try:
            return json.loads(clean)
        except Exception as e:
            partial_type = self._extract_partial_type(clean)
            if partial_type in ("project", "edit", "conversation"):
                return {
                    "type": partial_type,
                    "reason": "partial_json_recovery",
                }

            # Try to extract JSON object from text
            match = re.search(r'\{[^}]+\}', clean)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
            print("[Classifier] JSON decode failed:", clean[:100], e)
            return self._heuristic_intent(message, has_project=has_project)

    # Strong greenfield signals — if any match and there's no existing project, always "project".
    _PROJECT_SIGNALS = (
        "build", "create", "make", "generate", "design", "develop", "code",
        "website", "web app", "webapp", "landing page", "saas", "dashboard",
        "app", "application", "platform", "portfolio", "e-commerce", "ecommerce",
        "store", "blog", "forum", "chat app", "api", "backend", "frontend",
        "full-stack", "fullstack", "tool for", "system for", "a site",
    )

    def _is_strong_project_signal(self, message: str) -> bool:
        low = message.lower()
        return any(sig in low for sig in self._PROJECT_SIGNALS)

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

        if t == "conversation":
            heuristic = self._heuristic_intent(message, has_project=has_project)
            if heuristic.get("type") != "conversation":
                return heuristic

        if t == "edit" and not has_project:
            return {
                "type": "conversation",
                "reason": "edit_intent_without_project",
            }
        if t == "project" and has_project:
            # Cannot greenfield a second project into the same chat — treat as edit.
            return {
                "type": "edit",
                "reason": "project_intent_with_existing_project_coerced_to_edit",
            }
        if t not in ("project", "edit", "conversation"):
            intent["type"] = "conversation"
        return intent
