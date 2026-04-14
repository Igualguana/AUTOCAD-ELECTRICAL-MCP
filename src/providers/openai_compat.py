"""Generic OpenAI-compatible provider.

Works with any backend that exposes an OpenAI-compatible ``/chat/completions``
endpoint: OpenAI, Groq, LM Studio, Mistral, Together AI, Anyscale, etc.

The ``openai`` Python SDK is used, with the ``base_url`` set appropriately so
that the same code handles all of these services.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base import BaseProvider

logger = logging.getLogger(__name__)


class OpenAICompatProvider(BaseProvider):
    """Provider for OpenAI-compatible chat completion APIs.

    Parameters
    ----------
    api_key:
        API key.  For local servers like LM Studio the key is usually a
        placeholder (e.g. ``"lm-studio"``).
    base_url:
        Base URL for the API (default: ``"https://api.openai.com/v1"``).
    model:
        Model identifier (default: ``"gpt-4o"``).
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
    ) -> None:
        try:
            from openai import AsyncOpenAI, OpenAIError
            self._OpenAIError = OpenAIError
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for this provider. "
                "Run: pip install openai"
            ) from exc

        from openai import AsyncOpenAI

        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key or "sk-no-key",  # OpenAI SDK requires a non-empty key
            base_url=base_url,
        )

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """Send *messages* to the OpenAI-compatible endpoint and return the reply.

        Function / tool calls are serialised as readable text if returned by
        the model.
        """
        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            **kwargs,
        }
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = "auto"

        try:
            response = await self._client.chat.completions.create(**create_kwargs)
            return self._extract_text(response)
        except self._OpenAIError as exc:
            logger.error("OpenAI-compatible API error: %s", exc, exc_info=True)
            raise RuntimeError(f"API error from {self._model}: {exc}") from exc

    def get_model_name(self) -> str:
        return self._model

    @property
    def name(self) -> str:
        # Derive a readable name from the base_url
        url = str(self._client.base_url)
        if "openai.com" in url:
            return "openai"
        if "groq.com" in url:
            return "groq"
        if "localhost:1234" in url:
            return "lmstudio"
        return "openai_compat"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull the assistant's text (and any tool calls) from the response."""
        choice = response.choices[0]
        msg = choice.message
        parts: list[str] = []

        # Plain text content
        if msg.content:
            parts.append(msg.content)

        # Tool / function calls
        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn = tc.function
                parts.append(f"[Tool call: {fn.name}({fn.arguments})]")

        return "\n".join(parts) if parts else ""
