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
You are an ELITE software architect who designs systems for billion-dollar tech companies.
Your architecture decisions power platforms used by millions of users daily.

Analyze this full-stack project and create a COMPREHENSIVE architectural overview.

PROJECT IDEA:
{user_message}

PROJECT STRUCTURE:
{project_json}

YOUR TASK - Generate 3 components:

1. SYSTEM EXPLANATION (Detailed)
   - Overall architecture pattern (MVC, Layered, Microservices, etc.)
   - Data flow from user action to database and back
   - Key design decisions and why they were made
   - Scalability considerations
   - Security architecture overview

2. COMPONENT BREAKDOWN
   - Frontend: Key components, state management, routing
   - Backend: API structure, middleware, services layer
   - Database: Collections/schemas, relationships, indexing strategy
   - Integration: How frontend connects to backend

3. UML DIAGRAM (Mermaid format)
   - Show User → Frontend → Backend → Database flow
   - Include all major components
   - Show data flow arrows clearly
   - Group related components

RULES:
- Be PROFESSIONAL and TECHNICAL - this is documentation for senior engineers
- Use proper terminology (RESTful, async/await, state management, etc.)
- Diagram must accurately reflect the actual files in the project
- Think about production deployment, not just local dev

OUTPUT FORMAT (JSON ONLY):

{{
  "explanation": "Detailed 2-3 paragraph explanation of the architecture...",
  "component_breakdown": {{
    "frontend": "Detailed frontend architecture...",
    "backend": "Detailed backend architecture...",
    "database": "Database design and schema overview...",
    "integration": "How systems communicate..."
  }},
  "uml": "graph TD\\n    A[User Browser] -->|HTTP Request| B[React Frontend]\\n    B -->|API Call| C[FastAPI Backend]\\n    C -->|Query| D[(MongoDB)]\\n    D -->|Data| C\\n    C -->|JSON Response| B\\n    B -->|Render| A"
}}

Make this architecture documentation worthy of a technical design review at a top tech company.
"""

    def _parse_architecture_response(self, raw: str) -> dict:
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(clean)
            # Ensure all expected fields are present
            return {
                "explanation": parsed.get("explanation", "Architecture analysis completed."),
                "component_breakdown": parsed.get("component_breakdown", {
                    "frontend": "Frontend architecture details not available.",
                    "backend": "Backend architecture details not available.",
                    "database": "Database architecture details not available.",
                    "integration": "Integration details not available."
                }),
                "uml": parsed.get("uml", "graph TD\nA[Error] --> B[Parsing Failed]"),
            }
        except Exception:
            return {
                "explanation": "Failed to generate architecture explanation",
                "component_breakdown": {
                    "frontend": "Error parsing response",
                    "backend": "Error parsing response",
                    "database": "Error parsing response",
                    "integration": "Error parsing response"
                },
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
