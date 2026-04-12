from core.providers.openai_provider import OpenAIProvider

TOGETHER_BASE_URL = "https://api.together.xyz/v1"


class TogetherProvider(OpenAIProvider):
    name = "together"
    supports_streaming = True

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key=api_key, base_url=TOGETHER_BASE_URL)
