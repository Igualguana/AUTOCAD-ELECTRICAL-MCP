"""Abstract base class for all AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseProvider(ABC):
    """Defines the common interface that every AI provider must implement.

    Providers are responsible for sending messages (optionally with tool
    definitions) to an LLM backend and returning the model's response as a
    plain string.
    """

    # ------------------------------------------------------------------
    # Required interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """Send *messages* to the LLM and return the assistant's reply.

        Parameters
        ----------
        messages:
            A list of ``{"role": ..., "content": ...}`` dicts following the
            OpenAI chat format.
        tools:
            Optional list of tool/function definitions in the provider's
            expected schema.
        **kwargs:
            Provider-specific keyword arguments (temperature, top_p, etc.).

        Returns
        -------
        str
            The model's textual response.
        """

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier string (e.g. ``"claude-sonnet-4-6"``)."""

    # ------------------------------------------------------------------
    # Optional helpers with default implementations
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return a human-readable provider name (e.g. ``"claude"``)."""
        return self.__class__.__name__.replace("Provider", "").lower()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.get_model_name()!r})"
