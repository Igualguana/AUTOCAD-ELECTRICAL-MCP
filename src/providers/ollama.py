"""Ollama local models provider.

Supports the full Ollama library (200+ models). Uses the local Ollama REST API
at ``http://localhost:11434`` for chat/completion and the public Ollama registry
at ``https://ollama.com/api`` for library browsing and search.

Key capabilities
----------------
- Chat completions with streaming
- List locally installed models
- Search the public Ollama library
- Pull / delete models
- Show running models and GPU memory usage
- Get detailed model info (parameters, template, license)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Optional

import httpx

from .base import BaseProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Curated model catalog (offline fallback when ollama.com is unreachable)
# Keys = category label, values = list of (name, description, sizes)
# ---------------------------------------------------------------------------
OLLAMA_CATALOG: dict[str, list[dict[str, Any]]] = {
    "General Purpose": [
        {"name": "llama3.3",       "desc": "Meta Llama 3.3 — top general model",          "sizes": ["70b"]},
        {"name": "llama3.2",       "desc": "Meta Llama 3.2 — fast small models",           "sizes": ["1b", "3b"]},
        {"name": "llama3.1",       "desc": "Meta Llama 3.1 — 8B/70B/405B",                 "sizes": ["8b", "70b", "405b"]},
        {"name": "mistral",        "desc": "Mistral 7B — fast and capable",                "sizes": ["7b"]},
        {"name": "mistral-nemo",   "desc": "Mistral Nemo 12B — multilingual",              "sizes": ["12b"]},
        {"name": "mixtral",        "desc": "Mistral MoE — 8x7B / 8x22B",                  "sizes": ["8x7b", "8x22b"]},
        {"name": "gemma3",         "desc": "Google Gemma 3 — lightweight powerhouse",      "sizes": ["1b", "4b", "12b", "27b"]},
        {"name": "gemma2",         "desc": "Google Gemma 2 — efficient inference",         "sizes": ["2b", "9b", "27b"]},
        {"name": "phi4",           "desc": "Microsoft Phi-4 — small but mighty 14B",       "sizes": ["14b"]},
        {"name": "phi3.5",         "desc": "Microsoft Phi-3.5 — 3.8B MoE",                "sizes": ["3.8b"]},
        {"name": "qwen2.5",        "desc": "Alibaba Qwen 2.5 — multilingual",             "sizes": ["0.5b","1.5b","3b","7b","14b","32b","72b"]},
        {"name": "command-r",      "desc": "Cohere Command-R — enterprise RAG",            "sizes": ["35b"]},
        {"name": "command-r-plus", "desc": "Cohere Command-R+ — top enterprise model",    "sizes": ["104b"]},
        {"name": "aya",            "desc": "Cohere Aya — 23 languages",                    "sizes": ["8b", "35b"]},
        {"name": "falcon3",        "desc": "TII Falcon3 — open weights",                   "sizes": ["1b","3b","7b","10b"]},
        {"name": "internlm2",      "desc": "Shanghai AI Lab InternLM2",                    "sizes": ["1.8b","7b","20b"]},
    ],
    "Reasoning / Thinking": [
        {"name": "deepseek-r1",    "desc": "DeepSeek-R1 — open reasoning model",           "sizes": ["1.5b","7b","8b","14b","32b","70b","671b"]},
        {"name": "deepseek-v3",    "desc": "DeepSeek-V3 — MoE frontier model",             "sizes": ["671b"]},
        {"name": "qwq",            "desc": "Qwen QwQ-32B — strong reasoning",              "sizes": ["32b"]},
        {"name": "phi4-reasoning", "desc": "Microsoft Phi-4 Reasoning",                   "sizes": ["14b"]},
        {"name": "magistral",      "desc": "Mistral Magistral reasoning model",            "sizes": ["8b","24b"]},
        {"name": "openthinker",    "desc": "OpenThinker — open reasoning",                 "sizes": ["7b","32b"]},
        {"name": "exaone-deep",    "desc": "LG AI EXAONE-Deep reasoning",                  "sizes": ["2.4b","7.8b","32b"]},
        {"name": "skyT1",          "desc": "Sky-T1 reasoning model",                       "sizes": ["32b"]},
    ],
    "Coding": [
        {"name": "qwen2.5-coder",  "desc": "Qwen 2.5 Coder — best open coding model",     "sizes": ["0.5b","1.5b","3b","7b","14b","32b"]},
        {"name": "deepseek-coder-v2","desc": "DeepSeek Coder V2 — MoE coding",            "sizes": ["16b","236b"]},
        {"name": "codellama",      "desc": "Meta Code Llama",                              "sizes": ["7b","13b","34b","70b"]},
        {"name": "starcoder2",     "desc": "BigCode StarCoder2",                           "sizes": ["3b","7b","15b"]},
        {"name": "codegemma",      "desc": "Google CodeGemma",                             "sizes": ["2b","7b"]},
        {"name": "magicoder",      "desc": "OSS-Instruct Magicoder",                      "sizes": ["7b"]},
        {"name": "stable-code",    "desc": "Stability AI Stable Code",                    "sizes": ["3b"]},
        {"name": "granite-code",   "desc": "IBM Granite Code",                            "sizes": ["3b","8b","20b","34b"]},
        {"name": "yi-coder",       "desc": "01-AI Yi Coder",                              "sizes": ["1.5b","9b"]},
    ],
    "Vision / Multimodal": [
        {"name": "llama3.2-vision","desc": "Meta Llama 3.2 Vision — image understanding", "sizes": ["11b","90b"]},
        {"name": "llava",          "desc": "LLaVA — visual language model",               "sizes": ["7b","13b","34b"]},
        {"name": "llava-llama3",   "desc": "LLaVA with Llama 3 backbone",                "sizes": ["8b"]},
        {"name": "qwen2.5-vl",     "desc": "Qwen2.5 VL — vision language",              "sizes": ["3b","7b","32b","72b"]},
        {"name": "minicpm-v",      "desc": "MiniCPM-V — efficient multimodal",            "sizes": ["8b"]},
        {"name": "moondream",      "desc": "Moondream — tiny vision model",               "sizes": ["1.8b"]},
        {"name": "bakllava",       "desc": "BakLLaVA — Mistral + LLaVA",                 "sizes": ["7b"]},
        {"name": "gemma4",         "desc": "Google Gemma 4 multimodal",                  "sizes": ["4b","12b","27b"]},
        {"name": "granite3.2-vision","desc": "IBM Granite 3.2 Vision",                   "sizes": ["2b"]},
    ],
    "Embedding": [
        {"name": "nomic-embed-text",      "desc": "Nomic AI text embeddings",            "sizes": ["137m"]},
        {"name": "mxbai-embed-large",     "desc": "Mixed Bread large embeddings",        "sizes": ["335m"]},
        {"name": "snowflake-arctic-embed","desc": "Snowflake Arctic embeddings",         "sizes": ["22m","33m","110m","137m","335m"]},
        {"name": "bge-m3",                "desc": "BAAI BGE-M3 multilingual",            "sizes": ["567m"]},
        {"name": "all-minilm",            "desc": "All-MiniLM sentence transformers",    "sizes": ["22m","33m"]},
        {"name": "bge-large",             "desc": "BAAI BGE Large embeddings",           "sizes": ["335m"]},
        {"name": "nomic-embed-vision",    "desc": "Nomic AI vision embeddings",          "sizes": ["137m"]},
    ],
    "Tools / Function Calling": [
        {"name": "mistral",        "desc": "Mistral 7B — native tool use",               "sizes": ["7b"]},
        {"name": "qwen2.5",        "desc": "Qwen 2.5 — strong tool calling",             "sizes": ["7b","14b","32b","72b"]},
        {"name": "llama3.1",       "desc": "Llama 3.1 — built-in tool use",              "sizes": ["8b","70b"]},
        {"name": "firefunction-v2","desc": "Fireworks AI function calling",              "sizes": ["70b"]},
        {"name": "granite3.1-dense","desc": "IBM Granite 3.1 Dense — tools",            "sizes": ["2b","8b"]},
    ],
    "Small / Edge (< 4B)": [
        {"name": "llama3.2",       "desc": "Meta Llama 3.2",                             "sizes": ["1b","3b"]},
        {"name": "gemma3",         "desc": "Google Gemma 3",                             "sizes": ["1b"]},
        {"name": "phi3.5",         "desc": "Microsoft Phi-3.5 Mini",                    "sizes": ["3.8b"]},
        {"name": "qwen2.5",        "desc": "Alibaba Qwen 2.5",                          "sizes": ["0.5b","1.5b","3b"]},
        {"name": "smollm2",        "desc": "HuggingFace SmolLM2 — tiny",                "sizes": ["135m","360m","1.7b"]},
        {"name": "tinyllama",      "desc": "TinyLlama 1.1B — very fast",                "sizes": ["1.1b"]},
        {"name": "deepseek-r1",    "desc": "DeepSeek-R1 distilled",                     "sizes": ["1.5b"]},
        {"name": "moondream",      "desc": "Moondream vision mini",                     "sizes": ["1.8b"]},
    ],
    "Large / Frontier (70B+)": [
        {"name": "llama3.1",       "desc": "Meta Llama 3.1",                             "sizes": ["70b","405b"]},
        {"name": "llama3.3",       "desc": "Meta Llama 3.3",                             "sizes": ["70b"]},
        {"name": "deepseek-r1",    "desc": "DeepSeek-R1 full",                          "sizes": ["70b","671b"]},
        {"name": "deepseek-v3",    "desc": "DeepSeek-V3 MoE",                           "sizes": ["671b"]},
        {"name": "qwen2.5",        "desc": "Alibaba Qwen 2.5",                          "sizes": ["72b"]},
        {"name": "command-r-plus", "desc": "Cohere Command-R+",                         "sizes": ["104b"]},
        {"name": "mixtral",        "desc": "Mistral Mixtral",                           "sizes": ["8x22b"]},
        {"name": "codellama",      "desc": "Meta Code Llama",                           "sizes": ["70b"]},
    ],
    "Multilingual": [
        {"name": "qwen2.5",        "desc": "Qwen 2.5 — 29 languages",                   "sizes": ["7b","14b","32b","72b"]},
        {"name": "aya",            "desc": "Cohere Aya — 23 languages",                 "sizes": ["8b","35b"]},
        {"name": "mistral-nemo",   "desc": "Mistral Nemo — multilingual",               "sizes": ["12b"]},
        {"name": "gemma3",         "desc": "Google Gemma 3 — multilingual",             "sizes": ["4b","12b","27b"]},
        {"name": "orca2",          "desc": "Microsoft Orca 2",                          "sizes": ["7b","13b"]},
    ],
}


class OllamaProvider(BaseProvider):
    """Provider that sends requests to a local Ollama instance.

    Parameters
    ----------
    base_url:
        Base URL of the Ollama server (default: ``"http://localhost:11434"``).
    model:
        Model name as it appears in ``ollama list`` (default: ``"llama3.2"``).
    timeout:
        Request timeout in seconds (default: 120).
    """

    REGISTRY_URL = "https://ollama.com/api"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: int = 120,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """Send *messages* to Ollama and return the assistant's reply.

        Streaming is used internally so large responses don't time out,
        but the full text is assembled before returning.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }
        if tools:
            payload["tools"] = tools

        chunks: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        content = data.get("message", {}).get("content", "")
                        if content:
                            chunks.append(content)
                        if data.get("done"):
                            break
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Make sure Ollama is running: ollama serve"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:300]
            if status == 404:
                raise RuntimeError(
                    f"Ollama model '{self._model}' not found (HTTP 404). "
                    f"Pull it first: ollama pull {self._model}"
                ) from exc
            raise RuntimeError(
                f"Ollama API returned HTTP {status} for model '{self._model}': {body}"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise TimeoutError(
                f"Ollama model '{self._model}' timed out after {self._timeout}s "
                f"at {self._base_url}. "
                "The model may be too large for available RAM, or still loading. "
                "Try a smaller model (e.g. qwen2.5:0.5b) or increase timeout."
            ) from exc
        except httpx.WriteTimeout as exc:
            raise TimeoutError(
                f"Ollama write timeout sending request to '{self._model}' "
                f"at {self._base_url}."
            ) from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"Ollama connection to {self._base_url} timed out "
                f"({type(exc).__name__}) for model '{self._model}'. "
                "Ensure Ollama is running and the model is loaded."
            ) from exc

        raw = "".join(chunks)
        # Strip Qwen3-style chain-of-thought blocks (<think>...</think>)
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        return raw

    def get_model_name(self) -> str:
        return self._model

    @property
    def name(self) -> str:
        return "ollama"

    # ------------------------------------------------------------------
    # Local instance — installed models
    # ------------------------------------------------------------------

    async def list_models(self) -> list[dict[str, Any]]:
        """Return models installed locally with size and modification date.

        Returns
        -------
        list[dict]
            Each dict has keys: ``name``, ``size`` (bytes), ``modified_at``,
            ``digest``, ``details`` (family, parameter_size, quantization).
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                return resp.json().get("models", [])
        except Exception as exc:
            logger.warning("Could not list Ollama models: %s", exc)
            return []

    async def list_model_names(self) -> list[str]:
        """Return just the model names installed locally."""
        models = await self.list_models()
        return [m["name"] for m in models]

    async def get_model_info(self, model: str) -> dict[str, Any]:
        """Return detailed information about an installed model.

        Calls ``/api/show`` and returns the full model card including
        modelfile, parameters, template, and license.

        Parameters
        ----------
        model:
            Model name, e.g. ``"llama3.2:3b"`` or ``"deepseek-r1:7b"``.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self._base_url}/api/show",
                    json={"name": model},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"error": f"Model '{model}' is not installed locally. Pull it first."}
            raise
        except Exception as exc:
            return {"error": str(exc)}

    async def list_running_models(self) -> list[dict[str, Any]]:
        """Return models currently loaded in GPU/CPU memory.

        Returns
        -------
        list[dict]
            Each dict has keys: ``name``, ``size`` (bytes), ``size_vram``,
            ``expires_at``, ``digest``, ``details``.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self._base_url}/api/ps")
                resp.raise_for_status()
                return resp.json().get("models", [])
        except Exception as exc:
            logger.warning("Could not list running models: %s", exc)
            return []

    async def delete_model(self, model: str) -> dict[str, Any]:
        """Delete a locally installed model.

        Parameters
        ----------
        model:
            Model name, e.g. ``"llama3.2:3b"``.

        Returns
        -------
        dict
            ``{"success": True}`` on success or ``{"success": False, "error": ...}``.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    "DELETE",
                    f"{self._base_url}/api/delete",
                    json={"name": model},
                )
                if resp.status_code == 200:
                    return {"success": True, "model": model}
                return {"success": False, "error": resp.text, "status_code": resp.status_code}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Public registry — library browsing & pull
    # ------------------------------------------------------------------

    async def search_library(
        self,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search the public Ollama library at ollama.com.

        Falls back to searching the offline :data:`OLLAMA_CATALOG` if the
        registry is unreachable.

        Parameters
        ----------
        query:
            Search terms, e.g. ``"code"`` or ``"llama vision"``.
        limit:
            Maximum number of results to return (default 20).

        Returns
        -------
        list[dict]
            Each dict has keys: ``name``, ``description``, ``pull_count``,
            ``tag_count``, ``updated_at``.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.REGISTRY_URL}/search",
                    params={"q": query, "limit": limit},
                )
                resp.raise_for_status()
                data = resp.json()
                # Registry response format: {"models": [...]}
                models = data.get("models", data) if isinstance(data, dict) else data
                return models[:limit]
        except Exception as exc:
            logger.warning(
                "Ollama registry unreachable (%s), falling back to offline catalog.", exc
            )
            return self._search_offline_catalog(query, limit)

    def _search_offline_catalog(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search the bundled :data:`OLLAMA_CATALOG` when the registry is offline."""
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for category, models in OLLAMA_CATALOG.items():
            for m in models:
                if m["name"] in seen:
                    continue
                if (
                    query_lower in m["name"].lower()
                    or query_lower in m["desc"].lower()
                    or query_lower in category.lower()
                ):
                    results.append({
                        "name": m["name"],
                        "description": m["desc"],
                        "category": category,
                        "sizes": m["sizes"],
                        "source": "offline_catalog",
                    })
                    seen.add(m["name"])
                if len(results) >= limit:
                    return results
        return results

    def get_catalog(self) -> dict[str, list[dict[str, Any]]]:
        """Return the complete offline model catalog grouped by category.

        Useful for browsing all available models without a network request.
        """
        return OLLAMA_CATALOG

    def get_catalog_category(self, category: str) -> list[dict[str, Any]]:
        """Return models for a single catalog category (case-insensitive partial match).

        Parameters
        ----------
        category:
            Category name or prefix, e.g. ``"coding"`` or ``"vision"``.
        """
        category_lower = category.lower()
        for key, models in OLLAMA_CATALOG.items():
            if category_lower in key.lower():
                return models
        return []

    def list_categories(self) -> list[str]:
        """Return the list of model categories in the offline catalog."""
        return list(OLLAMA_CATALOG.keys())

    async def pull_model(self, model: str) -> AsyncIterator[dict[str, Any]]:
        """Stream progress while pulling a model from the Ollama registry.

        Yields
        ------
        dict
            Progress dicts with keys: ``status``, ``digest`` (optional),
            ``completed`` (bytes), ``total`` (bytes), ``percent`` (0-100).

        Example
        -------
        .. code-block:: python

            async for progress in provider.pull_model("llama3.2:3b"):
                print(progress["status"], progress.get("percent", ""))
        """
        payload = {"name": model, "stream": True}
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/pull",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    completed = data.get("completed", 0)
                    total = data.get("total", 0)
                    percent = round((completed / total) * 100, 1) if total > 0 else 0
                    yield {
                        "status": data.get("status", ""),
                        "digest": data.get("digest", ""),
                        "completed": completed,
                        "total": total,
                        "percent": percent,
                    }

    async def copy_model(self, source: str, destination: str) -> dict[str, Any]:
        """Copy a model to a new name (useful for creating custom variants).

        Parameters
        ----------
        source:
            Existing model name, e.g. ``"llama3.2"``.
        destination:
            New model name, e.g. ``"my-llama"``.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._base_url}/api/copy",
                    json={"source": source, "destination": destination},
                )
                if resp.status_code == 200:
                    return {"success": True, "source": source, "destination": destination}
                return {"success": False, "error": resp.text}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return ``True`` if the local Ollama server is reachable (synchronous)."""
        try:
            with httpx.Client(timeout=3) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
