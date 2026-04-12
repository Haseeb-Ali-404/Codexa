import re
import time

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


class PlannerAgent:
    """
    Generates step-by-step project plans via provider-agnostic LLM stack.
    Retries on transient overload; static fallback if all attempts fail.
    """

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
        max_retries: int = 3,
        retry_delays: tuple[int, ...] = (2, 5, 10),
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options
        self.max_retries = max_retries
        self.retry_delays = retry_delays

    def extract_title(self, raw_text: str) -> str:
        if not raw_text:
            return "Untitled Project"

        patterns = [
            r"\*\*Project Title[:\- ]*(.*?)\*\*",
            r"Project Title[:\- ]*(.*)",
            r"Title[:\- ]*(.*)",
        ]

        for pattern in patterns:
            m = re.search(pattern, raw_text, re.IGNORECASE)
            if m:
                return m.group(1).strip()

        m = re.search(r"\*\*(.*?)\*\*", raw_text)
        if m:
            candidate = m.group(1).strip()
            if not re.match(r"^\d+[\.\)]", candidate):
                return candidate

        for line in raw_text.splitlines():
            if line.strip():
                return line.strip()

        return "Untitled Project"

    def _clean_steps(self, raw_text: str) -> list[str]:
        if not raw_text:
            return []

        steps: list[str] = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue

            clean = re.sub(r"^(\d+[\.\)]|\-|\*|\•)\s*", "", line)
            clean = re.sub(r"[*_#>`~]", "", clean).strip()
            if clean:
                steps.append(clean)

        return steps

    def _plan_user_prompt(self, request: str) -> str:
        return (
            "You are an expert software architect. Break a medium-sized software project "
            "into clear, sequential, and actionable steps.\n"
            "Each step should represent a meaningful development milestone.\n"
            "Return only numbered steps, one per line — no explanations.\n\n"
            f"Project idea: {request}\n"
            "Also create a clear project title.\n"
        )

    def parse_plan_from_raw(self, raw_text: str) -> dict | None:
        raw_text = (raw_text or "").strip()
        if not raw_text:
            return None
        title = self.extract_title(raw_text)
        steps = self._clean_steps(raw_text)
        if not steps:
            return None
        return {"title": title, "steps": steps}

    async def astream_plan_text(self, request: str):
        """Stream raw plan text from the LLM (single attempt; for WS UX)."""
        messages = [ChatMessage(role="user", content=self._plan_user_prompt(request))]
        async for chunk in self._llm.acomplete_stream(messages, self._opts):
            if chunk:
                yield chunk

    def plan(self, request: str):
        print(f"🤔 Creating plan for: '{request}'")

        prompt = self._plan_user_prompt(request)

        messages = [ChatMessage(role="user", content=prompt)]
        last_error: str | None = None

        for attempt in range(self.max_retries):
            try:
                result = self._llm.complete(messages, self._opts)
                raw_text = result.text.strip() if result.text else ""
                if not raw_text:
                    raise RuntimeError("Empty response from model")

                title = self.extract_title(raw_text)
                steps = self._clean_steps(raw_text)

                if not steps:
                    raise RuntimeError("No valid steps extracted")

                print("📌 Extracted Title:", title)
                return {
                    "title": title,
                    "steps": steps,
                }

            except Exception as e:
                error_str = str(e)
                last_error = error_str

                if "503" in error_str or "UNAVAILABLE" in error_str:
                    print(
                        f"⚠️ Model overloaded (attempt {attempt + 1}/{self.max_retries}). "
                        "Retrying..."
                    )
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delays[attempt])
                        continue
                    break

                print(f"❌ Planner error: {error_str}")
                break

        print("⚠️ Planner failed. Using fallback plan.")
        print("Last error:", last_error)

        return {
            "title": "Generic Software Project",
            "steps": [
                "Define project requirements",
                "Design system architecture",
                "Set up backend structure",
                "Implement core backend features",
                "Build frontend interface",
                "Connect frontend with backend",
                "Test and debug the application",
                "Prepare the project for deployment",
            ],
        }
