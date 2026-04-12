from core.providers.openai_provider import OpenAIProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(OpenAIProvider):
    name = "groq"
    supports_streaming = True

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key=api_key, base_url=GROQ_BASE_URL)
