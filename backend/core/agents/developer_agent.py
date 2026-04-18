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
            print("[Developer] LLM output has unbalanced curly braces. Likely incomplete JSON.")
            raise ValueError(
                "LLM output is incomplete or truncated. Please try again or reduce output size."
            )

        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            json_str = json_match.group(0)
            if not braces_balanced(json_str):
                print("[Developer] Extracted JSON string has unbalanced braces. Likely incomplete JSON.")
                raise ValueError(
                    "Extracted JSON is incomplete or truncated. Please try again or reduce output size."
                )
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print("[Developer] Regex-extracted JSON still invalid:", e)

        # Fix common escape sequence issues from LLM
        cleaned = raw.replace("\\'", "'").replace('\\"', '"')
        # Fix any remaining invalid escapes (remove backslash before invalid chars)
        cleaned = cleaned.replace("\\\\", "\\")
        
        if braces_balanced(cleaned):
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                print("[Developer] All attempts to parse LLM output as JSON failed:", e)
                print("Raw output:\n", raw)
                raise e
        print("[Developer] Cleaned LLM output has unbalanced curly braces. Likely incomplete JSON.")
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
            print("[Developer] Failed to parse JSON from DeveloperAgent")
            print("Raw output:\n", raw)
            raise e

    def _build_developer_prompt(self, project_name: str, steps: list, user_message: str) -> str:
        prompt = f"""
    You are a senior full-stack engineer and product developer.

    ================================================
    CORE MINDSET
    ================================================
    - Build REAL, runnable products
    - Optimize for: clone → install → run → works
    - Minimize files but NEVER break architecture
    - Every file must have a clear purpose
    - Think in execution, not explanation

    ================================================
    INPUT
    ================================================
    USER IDEA:
    {user_message}

    PROJECT PLAN:
    """
        for step in steps:
            prompt += f"- {step}\n"

        prompt += """
    ================================================
    GLOBAL RULES
    ================================================
    - Generate ONLY runnable code
    - NO placeholders
    - NO comments
    - NO markdown
    - RETURN ONLY valid JSON

    ================================================
    CRITICAL: DEPENDENCY STRATEGY
    ================================================
    - Use EXACT versions (no ^, ~, latest)
    - Versions MUST be realistic and commonly used together
    - DO NOT guess unknown versions
    - Prefer known stable combinations
    - NEVER generate non-existent versions
    - The project MUST pass:
    npm install
    WITHOUT errors

    ================================================
    FRONTEND (STRICT)
    ================================================
    - React 18 + Vite + TypeScript
    - NO Tailwind
    - NO inline styles
    - CSS files only

    SAFE DEPENDENCIES (USE EXACTLY):
    - react: 18.2.0
    - react-dom: 18.2.0
    - vite: 5.0.10
    - @vitejs/plugin-react: 4.2.1
    - typescript: 5.3.3
    - @types/react: 18.2.61
    - @types/react-dom: 18.2.19

    RULES:
    - Do NOT force exact match between react and @types
    - If unsure about any @types → DO NOT include it

    ================================================
    FRONTEND STRUCTURE (STRICT)
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
    BACKEND (STRICT)
    ================================================
    - Python + FastAPI + MongoDB

    USE EXACT VERSIONS:
    - fastapi==0.109.2
    - uvicorn==0.27.1
    - motor==3.3.2
    - pymongo==4.6.1
    - pydantic==2.6.1

    RULES:
    - Use Pydantic v2 syntax ONLY
    - Proper request/response schemas
    - No broken imports

    ================================================
    BACKEND STRUCTURE
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
    API INTEGRATION RULE
    ================================================
    - Frontend MUST call:
    http://localhost:7979
    - Routes MUST match backend exactly

    ================================================
    FINAL VALIDATION (MANDATORY)
    ================================================
    Before output, ensure:

    - npm install works
    - vite dev runs
    - backend runs with uvicorn
    - no dependency conflicts
    - no missing imports

    If any issue exists → FIX before output

    ================================================
    OUTPUT FORMAT (STRICT)
    ================================================
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

    - Include ALL required files
    - Each file must contain FULL valid code
    - Project must run without manual fixes
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
        print("[DeveloperAgent] Generating full-stack project...")

        prompt = self._build_developer_prompt(project_name, steps, user_message)
        project_json = self._generate_json(prompt)

        if not isinstance(project_json, dict):
            raise RuntimeError("DeveloperAgent output is not a JSON object")

        if "structure" not in project_json:
            raise RuntimeError("DeveloperAgent output missing 'structure'")

        return project_json
