
import asyncio
import os
from core.providers.gemini_provider import GeminiProvider
from core.providers.base import ChatMessage, LLMCallOptions

async def test():
    provider = GeminiProvider(os.environ.get("GEMINI_API_KEY"))
    async for chunk in provider.acomplete_stream_parts([ChatMessage(role="user", content="list 3 steps")], "gemini-2.5-flash", LLMCallOptions()):
        print(f"chunk: {chunk}")

asyncio.run(test())
