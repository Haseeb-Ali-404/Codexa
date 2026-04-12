"""
Optional lazy Gemini client for legacy scripts.
Production code should use core.factory.create_agent(...).
"""

import os

from dotenv import load_dotenv

load_dotenv()

_client = None


def get_gemini_client():
    global _client
    if _client is None:
        from google import genai

        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is missing from environment")
        _client = genai.Client(api_key=key)
    return _client


class _LazyGemini:
    def __getattr__(self, name: str):
        return getattr(get_gemini_client(), name)


gemini = _LazyGemini()
