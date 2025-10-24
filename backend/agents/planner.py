import re
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import time

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)

class PlannerAgent:
    """Generates step-by-step project plans using Gemini API with robust handling and safe fallbacks."""

    def __init__(self, model_name="gemini-2.5-flash", max_output_tokens=2000):
        self.model_name = model_name
        self.client = client
        self.max_output_tokens = max_output_tokens

    def _extract_text_from_response(self, response) -> str | None:
        """Extract text safely from Gemini response."""
        if not response:
            return None

        # ✅ Primary: Direct text
        text = getattr(response, "text", None)
        if text and text.strip():
            return text.strip()

        # ✅ Fallback: Extract from first candidate if direct text missing
        candidates = getattr(response, "candidates", [])
        if candidates:
            content = getattr(candidates[0], "content", None)
            if content:
                parts = getattr(content, "parts", [])
                if parts:
                    # Combine only parts that actually have text
                    combined = "".join(
                        getattr(p, "text", "") for p in parts if getattr(p, "text", None)
                    ).strip()
                    if combined:
                        return combined

        return None

    def _clean_steps(self, raw_text: str) -> list[str]:
        """Convert Gemini output into a clean, numbered step list."""
        if not raw_text:
            return []

        lines = raw_text.splitlines()
        steps = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Remove numbers, bullets, or markdown formatting
            clean_line = re.sub(r"^(\d+[\.\)]|\-|\*|\•)\s*", "", line)
            clean_line = re.sub(r"[*_#>`~]", "", clean_line).strip()
            if clean_line:
                steps.append(clean_line)
        return steps

    def create_plan(self, request: str) -> list[str]:
        print(f"🤔 Creating plan for: '{request}'")

        prompt = (
            "You are an expert software architect. Break a medium-sized software project "
            "into clear, sequential, and actionable steps.\n"
            "Each step should represent a meaningful development milestone.\n"
            "Return only numbered steps, one per line — no explanations.\n\n"
            f"Project idea: {request}"
        )

        try:
            config = types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=self.max_output_tokens,
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            # Debug log of raw Gemini response (for troubleshooting)
            print("🧠 Gemini raw response received.")

            raw_text = self._extract_text_from_response(response)
            if raw_text:
                print("📝 Raw plan from Gemini:\n", raw_text)
                steps = self._clean_steps(raw_text)

                if steps:
                    print(f"✅ Plan created successfully! ({len(steps)} steps)")
                    return steps
                else:
                    print("⚠️ No valid steps extracted. Retrying...")

            else:
                print("⚠️ Gemini returned no text or incomplete output.")

        except Exception as e:
            print(f"❌ Error creating plan: {e}")

        # Fallback if Gemini gives no output or raises an exception
        print("⚠️ Using fallback default plan.")
        return [
            "Define project requirements",
            "Design system architecture",
            "Develop backend logic",
            "Build frontend interface",
            "Integrate backend and frontend",
            "Test and debug the system",
            "Deploy and maintain the project"
        ]
