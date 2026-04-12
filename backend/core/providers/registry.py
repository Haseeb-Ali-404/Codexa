from __future__ import annotations

from core.providers.base import LLMProvider

_CUSTOM_PROVIDERS: dict[str, type[LLMProvider]] = {}


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    """Register a custom provider (class must accept api_key: str)."""
    _CUSTOM_PROVIDERS[name.lower().strip()] = cls


def build_provider(provider_id: str, api_key: str) -> LLMProvider:
    key = provider_id.lower().strip()
    if key in _CUSTOM_PROVIDERS:
        return _CUSTOM_PROVIDERS[key](api_key)
    if key == "openai":
        from core.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key)
    if key in ("gemini", "google"):
        from core.providers.gemini_provider import GeminiProvider

        return GeminiProvider(api_key)
    if key == "anthropic":
        from core.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key)
    if key == "groq":
        from core.providers.groq_provider import GroqProvider

        return GroqProvider(api_key)
    if key == "together":
        from core.providers.together_provider import TogetherProvider

        return TogetherProvider(api_key)
    raise ValueError(f"Unknown LLM provider: {provider_id!r}")
