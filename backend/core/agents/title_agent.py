import json

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


class TitleAgent:
    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    def generate_title(self, message: str, max_len: int = 60) -> str:
        prompt = f"""
Your name is CODEXA.
Generate a short title for this message:

"{message}"

Respond ONLY in valid JSON like this:
{{"title": "Your generated title"}}
"""
        messages = [ChatMessage(role="user", content=prompt)]
        try:
            result = self._llm.complete(messages, self._opts)
            raw = result.text.strip()
        except Exception as e:
            print("Title generation error:", e)
            return "Untitled Project"

        raw = raw.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(raw)
            title = data.get("title", "").strip()
            if title:
                return title[:max_len]
        except Exception as e:
            print("JSON Parse Error:", e, "Raw:", raw)

        return "Untitled Project"
