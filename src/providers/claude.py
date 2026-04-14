"""Anthropic Claude provider.

Uses the official ``anthropic`` Python SDK to call the Claude API with full
support for tool_use (function calling).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base import BaseProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseProvider):
    """Provider that sends requests to Anthropic's Claude API.

    Parameters
    ----------
    api_key:
        Anthropic API key.  If empty, the ``ANTHROPIC_API_KEY`` environment
        variable will be used by the SDK automatically.
    model:
        Claude model identifier (default: ``"claude-sonnet-4-6"``).
    max_tokens:
        Maximum tokens in the assistant's response.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
    ) -> None:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for the Claude provider. "
                "Run: pip install anthropic"
            ) from exc

        self._anthropic = _anthropic
        self._model = model
        self._max_tokens = max_tokens

        # Create the client; the SDK will use ANTHROPIC_API_KEY env var if
        # api_key is an empty string.
        self._client = _anthropic.Anthropic(api_key=api_key or None)

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """Send *messages* to Claude and return the assistant's text reply.

        If *tools* are provided they are forwarded as Claude tool definitions
        and any ``tool_use`` blocks are serialised back as text for the caller.
        """
        # Separate a system message if present (Claude API handles it separately)
        system_content = ""
        filtered_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": filtered_messages,
            **kwargs,
        }
        if system_content:
            create_kwargs["system"] = system_content
        if tools:
            create_kwargs["tools"] = self._convert_tools(tools)

        try:
            response = self._client.messages.create(**create_kwargs)
            return self._extract_text(response)
        except self._anthropic.APIConnectionError as exc:
            raise ConnectionError(f"Claude API connection error: {exc}") from exc
        except self._anthropic.AuthenticationError as exc:
            raise PermissionError(f"Claude API authentication failed: {exc}") from exc
        except self._anthropic.RateLimitError as exc:
            raise RuntimeError(f"Claude API rate limit exceeded: {exc}") from exc
        except Exception as exc:
            logger.error("Claude API error: %s", exc, exc_info=True)
            raise

    def get_model_name(self) -> str:
        return self._model

    @property
    def name(self) -> str:
        return "claude"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_text(self, response: Any) -> str:
        """Extract plain text from a Claude Messages API response."""
        parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
            elif block.type == "tool_use":
                # Serialise tool calls as readable text
                parts.append(
                    f"[Tool call: {block.name}({block.input})]"
                )
        return "\n".join(parts)

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert generic tool dicts to Claude's tool definition format.

        Generic format (OpenAI-style)::

            {
              "type": "function",
              "function": {
                "name": "...",
                "description": "...",
                "parameters": { ... }   # JSON Schema
              }
            }

        Claude format::

            {
              "name": "...",
              "description": "...",
              "input_schema": { ... }   # JSON Schema
            }
        """
        claude_tools = []
        for tool in tools:
            if "function" in tool:
                fn = tool["function"]
                claude_tools.append(
                    {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {"type": "object"}),
                    }
                )
            else:
                # Already in Claude format or unknown – pass through as-is
                claude_tools.append(tool)
        return claude_tools
