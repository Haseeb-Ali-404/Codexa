import json

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


class ArchitectAgent:
    """Generates explanation + Mermaid UML from developer output."""

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    @staticmethod
    def _architecture_prompt(project_json: dict, user_message: str) -> str:
        return f"""
You are a senior software architect.

Analyze the following full-stack project structure and generate:

1. A clear, concise explanation of the system
2. A UML diagram in Mermaid format

RULES:
- No markdown except Mermaid block
- Keep explanation simple but professional
- UML must reflect frontend → backend → database flow
- Do NOT hallucinate files not present

PROJECT IDEA:
{user_message}

PROJECT JSON:
{project_json}

OUTPUT FORMAT:

{{
  "explanation": "...",
  "uml": "graph TD\\n A --> B"
}}
"""

    def _parse_architecture_response(self, raw: str) -> dict:
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except Exception:
            return {
                "explanation": "Failed to generate architecture explanation",
                "uml": "graph TD\nA[Error] --> B[Parsing Failed]",
            }

    def generate_architecture(self, project_json: dict, user_message: str):
        messages = [
            ChatMessage(
                role="user",
                content=self._architecture_prompt(project_json, user_message),
            )
        ]
        result = self._llm.complete(messages, self._opts)
        return self._parse_architecture_response(result.text.strip())

    async def agenerate_architecture(self, project_json: dict, user_message: str) -> dict:
        messages = [
            ChatMessage(
                role="user",
                content=self._architecture_prompt(project_json, user_message),
            )
        ]
        result = await self._llm.acomplete_text(messages, self._opts)
        return self._parse_architecture_response(result.text.strip())
