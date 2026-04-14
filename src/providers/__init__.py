"""AI provider package for AutoCAD Electrical MCP Server."""

from .base import BaseProvider
from .claude import ClaudeProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider


def get_provider(config=None) -> BaseProvider:
    """Factory: return the active provider based on configuration.

    Parameters
    ----------
    config:
        A :class:`~src.config.Config` instance.  When ``None``, the
        module-level singleton is used.
    """
    from src.config import get_config

    if config is None:
        config = get_config()

    provider_name = config.get_active_provider()
    provider_cfg = config.get_provider_config(provider_name)

    if provider_name == "claude":
        return ClaudeProvider(
            api_key=provider_cfg.get("api_key", ""),
            model=provider_cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=provider_cfg.get("max_tokens", 8192),
        )
    elif provider_name == "ollama":
        return OllamaProvider(
            base_url=provider_cfg.get("base_url", "http://localhost:11434"),
            model=provider_cfg.get("model", "llama3.2"),
            timeout=provider_cfg.get("timeout", 120),
        )
    else:
        # openai | groq | lmstudio or any OpenAI-compatible endpoint
        return OpenAICompatProvider(
            api_key=provider_cfg.get("api_key", ""),
            base_url=provider_cfg.get("base_url", "https://api.openai.com/v1"),
            model=provider_cfg.get("model", "gpt-4o"),
        )


__all__ = [
    "BaseProvider",
    "ClaudeProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "get_provider",
]
