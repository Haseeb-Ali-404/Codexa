import json
import re
from difflib import SequenceMatcher

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


def _classifier_log(message: str) -> None:
    print(f"[Classifier] {message}", flush=True)


class ClassifierAgent:
    CLASSIFIER_PROMPT = """
You are an intent classifier for CODEXA (AI coding IDE).

Context:
{context_note}

Classify ONLY the user's intent. Pick exactly one type.

DECISION RULES (apply in order):

1. If a project is already linked to this chat and the user wants any actionable change to that project, choose "edit".
   Actionable edit signals include changing, updating, modifying, fixing, adding, removing, renaming, restyling, moving, replacing, or adjusting code/UI/content.

2. If the user is asking for a complete mini app that can reasonably be implemented as a single self-contained HTML file with inline CSS and JavaScript, choose "small_project".
   Examples: calculator, stopwatch, timer, quiz, calendar UI, todo app, counter, notes widget, landing page, portfolio, pricing page.
   IMPORTANT: if the request asks for both the app and an explanation or breakdown, still choose "small_project".
   IMPORTANT: this still applies even when a project is already linked to the chat, unless the user clearly asks to apply it to the current project/app.

3. If no project is linked yet and the user is asking for a larger greenfield application that likely needs multiple files, framework setup, backend, database, auth, APIs, or broader app architecture, choose "project".

4. Otherwise choose "conversation".

CONVERSATION means:
- code snippets
- explanations
- debugging help
- partial implementations
- questions, clarifications, general chat

IMPORTANT:
- When a project already exists, use "edit" for actionable requests to that current project, "conversation" for pure questions/snippets, and "small_project" for a clearly fresh standalone mini app request.
- If classification is ambiguous, default to "conversation".
- Prioritize "small_project" over "conversation" whenever the user is clearly asking for a complete usable mini app.

Examples:
- "Explain binary search with code" -> conversation
- "Fix this function" -> conversation
- "Give me a login API example with explanation" -> conversation
- "Build a calculator" -> small_project
- "Make a calendar UI" -> small_project
- "Create a todo app and explain it" -> small_project
- "Build a React SaaS dashboard with auth and API" -> project
- "Add dark mode" (project exists) -> edit
- "Why did you use Zustand?" (project exists) -> conversation

Your response MUST be ONLY valid JSON. No markdown, no comments, no text outside JSON.

JSON FORMAT:
{
  "type": "<project|small_project|edit|conversation>",
  "reason": "short"
}

User message:
{message}
"""

    _TYPE_RE = re.compile(
        r'"type"\s*:\s*"?(project|small_project|edit|conversation)?',
        re.IGNORECASE,
    )
    _ACTIONABLE_EDIT_SIGNALS = (
        "change", "update", "modify", "edit", "add", "remove", "delete", "fix",
        "rename", "replace", "restyle", "improve", "refactor", "make it", "make the",
        "style", "color", "bigger", "smaller", "move", "also include", "use", "put",
        "show", "hide", "button", "navbar", "header", "footer", "page", "component",
        "layout", "spacing", "font", "theme", "dark mode",
    )
    _QUESTION_SIGNALS = (
        "explain", "what is", "what does", "why", "how does", "how do",
        "can you explain", "help me understand", "walk me through",
    )
    _CONVERSATION_SIGNALS = (
        "snippet", "code snippet", "example", "debug", "debugging",
        "fix this function", "fix this code", "partial implementation",
    )
    _SNIPPET_REQUEST_SIGNALS = (
        "give me code", "provide code", "show me code", "show code",
        "write code", "code for", "code to", "sample code", "example code",
        "code example", "function for", "function to", "utility for",
        "snippet for", "snippet to", "algorithm", "reverse a string",
    )
    _PROJECT_EDIT_CONTEXT_SIGNALS = (
        "in this project", "in the project", "for this project", "inside this project",
        "in my project", "inside my project", "in this app", "in the app",
        "for this app", "inside this app", "in my app", "apply this to the project",
        "apply this to the app", "integrate this", "update the project",
        "modify the project", "change the project", "edit the project",
        "update the app", "modify the app", "change the app", "edit the app",
    )
    _BUILD_SIGNALS = (
        "build", "create", "make", "generate", "design", "develop",
        "code", "implement", "craft", "recreate", "rebuild", "regenerate",
        "remake", "redo",
    )
    _SMALL_PROJECT_NOUNS = (
        "calculator", "calaculator", "stopwatch", "timer", "todo", "todo app", "to-do",
        "calendar", "calendar ui", "counter", "quiz", "notes app", "notes widget",
        "weather app", "weather widget", "landing page", "portfolio", "pricing page",
        "form", "converter", "expense tracker", "kanban board", "music player",
    )
    _COMPLEX_PROJECT_SIGNALS = (
        "backend", "api", "database", "postgres", "mysql", "mongodb", "auth",
        "authentication", "login system", "signup", "sign up", "full stack",
        "full-stack", "react", "next.js", "nextjs", "vue", "angular", "express",
        "fastapi", "django", "microservice", "websocket", "real-time", "realtime",
        "multi-page", "multi file", "multi-file", "admin dashboard", "saas platform",
        "deploy", "docker", "payments", "stripe", "cms",
    )
    _PROJECT_SIGNALS = (
        "website", "web app", "webapp", "dashboard", "saas", "platform",
        "application", "app", "portal", "system", "tool",
    )

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    def _normalize(self, message: str) -> str:
        return " ".join((message or "").strip().lower().split())

    def _contains_any(self, text: str, signals: tuple[str, ...]) -> bool:
        return any(signal in text for signal in signals)

    def _contains_small_project_noun(self, text: str) -> bool:
        if self._contains_any(text, self._SMALL_PROJECT_NOUNS):
            return True

        candidate_words = {
            word
            for noun in self._SMALL_PROJECT_NOUNS
            for word in re.findall(r"[a-z0-9]+", noun)
            if len(word) >= 5 and word not in {"widget"}
        }
        for token in re.findall(r"[a-z0-9]+", text):
            if len(token) < 5:
                continue
            for word in candidate_words:
                if token[0] != word[0]:
                    continue
                if abs(len(token) - len(word)) > 2:
                    continue
                if SequenceMatcher(None, token, word).ratio() >= 0.84:
                    return True
        return False

    def _looks_like_pure_question(self, text: str) -> bool:
        if not text:
            return False
        return (
            text.endswith("?")
            or self._contains_any(text, self._QUESTION_SIGNALS)
            or text.startswith(("why ", "how ", "what ", "when ", "where "))
        )

    def _looks_like_conversation_request(self, text: str) -> bool:
        if not text:
            return True
        if self._looks_like_pure_question(text):
            return True
        if self._contains_any(text, self._CONVERSATION_SIGNALS):
            return True
        if self._contains_any(text, self._SNIPPET_REQUEST_SIGNALS):
            return True
        if "with code" in text and not self._contains_any(text, self._BUILD_SIGNALS):
            return True
        return False

    def _looks_like_snippet_request(self, text: str) -> bool:
        if not text:
            return False
        if self._contains_any(text, self._SNIPPET_REQUEST_SIGNALS):
            return True
        return (
            ("code" in text or "function" in text or "snippet" in text)
            and not self._contains_any(text, self._PROJECT_EDIT_CONTEXT_SIGNALS)
            and not self._contains_small_project_noun(text)
        )

    def _looks_like_existing_project_edit(self, text: str) -> bool:
        if not text:
            return False
        if self._looks_like_small_project(text):
            return False
        if self._looks_like_snippet_request(text) or self._looks_like_conversation_request(text):
            return False
        if self._contains_any(text, self._PROJECT_EDIT_CONTEXT_SIGNALS):
            return True
        return self._contains_any(text, self._ACTIONABLE_EDIT_SIGNALS)

    def _looks_like_small_project(self, text: str) -> bool:
        if not text:
            return False
        if self._contains_any(text, self._COMPLEX_PROJECT_SIGNALS):
            return False
        if "single html" in text or "single file" in text or "single-page" in text:
            return True
        has_small_noun = self._contains_small_project_noun(text)
        has_build_signal = self._contains_any(text, self._BUILD_SIGNALS)
        return has_small_noun and (has_build_signal or len(text.split()) <= 10)

    def _looks_like_large_project(self, text: str) -> bool:
        if not text:
            return False
        if self._contains_any(text, self._COMPLEX_PROJECT_SIGNALS):
            return True
        return self._contains_any(text, self._PROJECT_SIGNALS) and self._contains_any(
            text, self._BUILD_SIGNALS
        )

    def _heuristic_intent(self, message: str, *, has_project: bool = False) -> dict:
        low = self._normalize(message)
        if not low:
            return {
                "type": "conversation",
                "reason": "empty_message",
            }

        if has_project:
            if self._looks_like_pure_question(low) or self._looks_like_snippet_request(low):
                return {
                    "type": "conversation",
                    "reason": "question_in_existing_project_chat",
                }
            if self._looks_like_existing_project_edit(low):
                return {
                    "type": "edit",
                    "reason": "actionable_request_in_existing_project_chat",
                }
            if self._looks_like_small_project(low):
                return {
                    "type": "small_project",
                    "reason": "fresh_small_project_request_in_existing_chat",
                }
            if (
                self._looks_like_large_project(low)
                and not self._contains_any(low, self._PROJECT_EDIT_CONTEXT_SIGNALS)
            ):
                return {
                    "type": "project",
                    "reason": "fresh_large_project_request_in_existing_chat",
                }
            return {
                "type": "conversation",
                "reason": "existing_project_conversation_fallback",
            }

        if self._looks_like_small_project(low):
            return {
                "type": "small_project",
                "reason": "single_file_app_signal",
            }

        if self._looks_like_large_project(low):
            return {
                "type": "project",
                "reason": "multi_file_project_signal",
            }

        if self._looks_like_conversation_request(low):
            return {
                "type": "conversation",
                "reason": "conversation_signal",
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
        if has_project:
            intent = self._heuristic_intent(message, has_project=True)
            _classifier_log(
                f"existing-project heuristic type={intent.get('type')} reason={intent.get('reason')}"
            )
            return intent

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
            _classifier_log(f"model response={raw}")
        except Exception as e:
            _classifier_log(f"error={e}")
            return {
                "type": "conversation",
                "reason": "model_call_failed",
            }

        clean = raw
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```", 1)[0]
        clean = clean.strip()

        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            partial_type = self._extract_partial_type(clean)
            if partial_type in ("project", "small_project", "edit", "conversation"):
                return {
                    "type": partial_type,
                    "reason": "partial_json_recovery",
                }

            match = re.search(r"\{[^}]+\}", clean)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass

            _classifier_log(f"json decode failed raw={clean[:100]} err={e}")
            return self._heuristic_intent(message, has_project=has_project)

        intent = self._heuristic_intent(message, has_project=has_project)
        _classifier_log(
            f"fallback heuristic type={intent.get('type')} reason={intent.get('reason')}"
        )
        return intent

    def classify_for_project(
        self,
        message: str,
        chat_id: str | None,
        *,
        has_project: bool = False,
    ):
        del chat_id
        intent = self.classify(message, has_project=has_project)
        _classifier_log(
            f"classify_for_project initial type={intent.get('type')} reason={intent.get('reason')}"
        )
        t = intent.get("type")

        if has_project:
            heuristic = self._heuristic_intent(message, has_project=True)
            if heuristic.get("type") in ("edit", "conversation", "small_project"):
                return heuristic

        if t == "conversation":
            heuristic = self._heuristic_intent(message, has_project=has_project)
            if heuristic.get("type") != "conversation":
                return heuristic

        if t == "edit" and not has_project:
            heuristic = self._heuristic_intent(message, has_project=False)
            if heuristic.get("type") in ("small_project", "project"):
                return heuristic
            return {
                "type": "conversation",
                "reason": "edit_intent_without_project",
            }
        if t not in ("project", "small_project", "edit", "conversation"):
            intent["type"] = "conversation"
        _classifier_log(
            f"classify_for_project final type={intent.get('type')} reason={intent.get('reason')}"
        )
        return intent
