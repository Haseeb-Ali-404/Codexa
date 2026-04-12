import json
import re

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


class DeveloperAgent:
    """
    Generates a multi-folder, full-stack project as strict JSON via any LLM provider.
    """

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    def _parse_llm_output(self, raw: object) -> dict:
        if isinstance(raw, dict):
            return raw

        if not isinstance(raw, str):
            raise TypeError(f"Unexpected LLM output type: {type(raw)}")

        raw = raw.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        def braces_balanced(s: str) -> bool:
            return s.count("{") == s.count("}")

        if braces_balanced(raw):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        else:
            print("❌ LLM output has unbalanced curly braces. Likely incomplete JSON.")
            raise ValueError(
                "LLM output is incomplete or truncated. Please try again or reduce output size."
            )

        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            json_str = json_match.group(0)
            if not braces_balanced(json_str):
                print("❌ Extracted JSON string has unbalanced braces. Likely incomplete JSON.")
                raise ValueError(
                    "Extracted JSON is incomplete or truncated. Please try again or reduce output size."
                )
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print("❌ Regex-extracted JSON still invalid:", e)

        cleaned = raw.replace("\\'", "'")
        if braces_balanced(cleaned):
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                print("❌ All attempts to parse LLM output as JSON failed:", e)
                print("Raw output:\n", raw)
                raise e
        print("❌ Cleaned LLM output has unbalanced curly braces. Likely incomplete JSON.")
        raise ValueError(
            "LLM output is incomplete or truncated after cleaning. Please try again or reduce output size."
        )

    def _generate_json(self, prompt: str) -> dict:
        messages = [ChatMessage(role="user", content=prompt)]
        result = self._llm.complete(messages, self._opts)
        raw = result.text
        if raw is None or not str(raw).strip():
            raise RuntimeError("LLM returned no text output")
        try:
            return self._parse_llm_output(raw)
        except Exception as e:
            print("❌ Failed to parse JSON from DeveloperAgent")
            print("Raw output:\n", raw)
            raise e

    def _build_developer_prompt(self, project_name: str, steps: list, user_message: str) -> str:
        _ = project_name
        prompt = f"""
You are a senior full-stack engineer and product developer.

You behave like:
- Lovable.dev
- Bolt.new
- Google AI Studio (Code generation mode)

Your mindset:
- You think in terms of real products, not demos
- You generate the MINIMUM number of files required to build a complete, working product
- Every file you generate must have a clear purpose
- You avoid unnecessary abstraction
- You follow real-world best practices
- You assume another developer will run this project immediately
- You assume the project will be executed automatically without manual fixes

Decision rules:
- Do NOT over-engineer
- Do NOT create unused files
- Do NOT repeat logic
- Prefer clarity over cleverness
- Prefer fewer files over many files (but never fewer than required)
- Prefer stability over novelty

You are confident, opinionated, and precise.
You think like a platform engineer, not a tutorial author.

Your task is to generate a REAL, PRODUCTION-READY,
MULTI-FOLDER FULL-STACK SOFTWARE PROJECT.

USER IDEA:
{user_message}

PROJECT PLAN:
"""
        for step in steps:
            prompt += f"- {step}\n"
        prompt += """
STRICT REQUIREMENTS (DO NOT VIOLATE):

================================================
GENERAL RULES:
================================================
- Generate REAL, runnable code
- NO placeholders
- NO inline CSS
- NO Tailwind CSS
- NO Create React App
- NO Next.js
- NO explanations
- NO markdown
- NO comments
- RETURN ONLY VALID JSON
- Assume the code will be executed immediately after generation

================================================
FRONTEND REQUIREMENTS (VERY STRICT):
================================================
- Framework: React 18 + Vite
- Language: TypeScript (TSX)
- Backend Port: 7979
- Styling: Plain external CSS files ONLY
- Entry file: src/main.tsx (Vite standard)
- Functional components only
- Clean and realistic UI (via CSS files only)

DEPENDENCY STABILITY RULES (NON-NEGOTIABLE):
- NEVER use "latest", "^", "~", or loose semver ranges
- ALL dependencies MUST be pinned to exact versions
- Use only stable, widely adopted versions
- Avoid experimental, beta, or recently released versions
- Avoid unnecessary build tools, polyfills, or Babel plugins
- Minimize transitive dependencies

REACT + VITE SAFE BASELINE (FOLLOW THIS):
- react: 18.2.0
- react-dom: 18.2.0
- vite: 5.0.x (stable)
- @vitejs/plugin-react: 4.x (stable)
- @types/react: pinned
- @types/react-dom: pinned

Do NOT add extra frontend dependencies unless absolutely required.

================================================
FRONTEND STRUCTURE (MUST MATCH EXACTLY):
================================================
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.node.json
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    ├── components/
    └── pages/

================================================
BACKEND REQUIREMENTS:
================================================
- Language: Python
- Framework: FastAPI
- Database: MongoDB (motor or pymongo)
- Proper API routing
- Proper project structure
- Entry point MUST be backend/main.py with `app = FastAPI()`
- Backend must be runnable without modification

================================================
BACKEND STRUCTURE (MUST MATCH):
================================================
backend/
├── main.py
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   ├── routes.py
│   └── schemas.py

================================================
OUTPUT FORMAT (VERY IMPORTANT):
================================================
RETURN ONLY VALID JSON IN THIS EXACT FORMAT:

{
    "project_type": "fullstack",
    "structure": [
        {
            "type": "folder",
            "name": "frontend",
            "children": []
        },
        {
            "type": "folder",
            "name": "backend",
            "children": []
        }
    ]
}

RULES FOR FILES ARRAY:
- Every required file must be included
- Each file must contain FULL, VALID code
- File paths must be valid (no spaces, no special characters)
- CSS must be in .css files ONLY
- The project MUST run without manual dependency fixes
"""
        return prompt

    async def astream_developer_text(
        self, project_name: str, steps: list, user_message: str
    ):
        """Stream raw JSON text from the LLM (WebSocket UX)."""
        prompt = self._build_developer_prompt(project_name, steps, user_message)
        messages = [ChatMessage(role="user", content=prompt)]
        async for chunk in self._llm.acomplete_stream(messages, self._opts):
            if chunk:
                yield chunk

    def parse_project_from_raw(self, raw: str) -> dict:
        return self._parse_llm_output(raw)

    def generate_project(self, project_name: str, steps: list, user_message: str):
        print("🧑‍💻 DeveloperAgent generating full-stack project...")

        prompt = self._build_developer_prompt(project_name, steps, user_message)
        project_json = self._generate_json(prompt)

        if not isinstance(project_json, dict):
            raise RuntimeError("DeveloperAgent output is not a JSON object")

        if "structure" not in project_json:
            raise RuntimeError("DeveloperAgent output missing 'structure'")

        return project_json
