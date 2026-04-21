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
        prompt = f"""Extract the project/app name from this request and generate a title in the format: "AppName - brief tagline".

Rules:
- If the user named the app (e.g. "build Luminos"), use that name exactly.
- If no name given, invent a short catchy brand name for the app type.
- Tagline: 3-6 words describing what it is (e.g. "a modern SaaS platform", "an e-commerce store").
- Total title must be under 60 characters.

User request: "{message}"

Respond ONLY in valid JSON:
{{"title": "AppName - brief tagline"}}
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
