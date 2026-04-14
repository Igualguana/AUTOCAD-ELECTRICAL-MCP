"""Configuration loader for AutoCAD Electrical MCP Server.

Reads config.yaml and .env, resolves ${VAR} environment variable references,
and provides typed access to all configuration sections.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Locate the project root (parent of src/)
_PROJECT_ROOT = Path(__file__).parent.parent


def _resolve_env_refs(value: Any) -> Any:
    """Recursively resolve ${VAR} placeholders in strings using environment variables."""
    if isinstance(value, str):
        def _replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))  # leave as-is if not set
        return re.sub(r"\$\{([^}]+)\}", _replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_refs(item) for item in value]
    return value


class Config:
    """Central configuration object.

    Loads ``config.yaml`` from the project root and the ``.env`` file (if
    present), then exposes each config section as a typed dictionary.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        # Load .env first so env vars are available for ${VAR} resolution
        env_path = _PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            load_dotenv()  # try default locations

        if config_path is None:
            config_path = _PROJECT_ROOT / "config.yaml"

        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        # Allow ACTIVE_PROVIDER env var to override config.yaml
        if os.environ.get("ACTIVE_PROVIDER"):
            raw["active_provider"] = os.environ["ACTIVE_PROVIDER"]

        self._data: dict[str, Any] = _resolve_env_refs(raw)

    # ------------------------------------------------------------------
    # Top-level section accessors
    # ------------------------------------------------------------------

    @property
    def active_provider(self) -> str:
        return self._data.get("active_provider", "claude")

    @active_provider.setter
    def active_provider(self, value: str) -> None:
        self._data["active_provider"] = value

    @property
    def providers(self) -> dict[str, Any]:
        return self._data.get("providers", {})

    @property
    def autocad(self) -> dict[str, Any]:
        return self._data.get("autocad", {})

    @property
    def mcp(self) -> dict[str, Any]:
        return self._data.get("mcp", {})

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_provider_config(self, provider: str | None = None) -> dict[str, Any]:
        """Return the configuration dict for *provider* (defaults to active)."""
        name = provider or self.active_provider
        cfg = self.providers.get(name)
        if cfg is None:
            raise KeyError(f"Provider '{name}' is not defined in config.yaml")
        return cfg

    def get_active_provider(self) -> str:
        """Return the name of the currently active provider."""
        return self.active_provider

    def list_providers(self) -> list[str]:
        return list(self.providers.keys())

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def save(self, config_path: str | Path | None = None) -> None:
        """Persist the current in-memory config back to config.yaml.

        Note: ${VAR} placeholders that were already resolved at load time are
        *not* re-serialised as placeholders—this method is intended for
        programmatic changes such as ``switch_model`` updating the active
        provider.
        """
        if config_path is None:
            config_path = _PROJECT_ROOT / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(self._data, fh, default_flow_style=False, sort_keys=False)


# Module-level singleton – import and use directly in other modules.
_config_instance: Config | None = None


def get_config(reload: bool = False) -> Config:
    """Return the module-level :class:`Config` singleton.

    Parameters
    ----------
    reload:
        When ``True``, discard the cached instance and reload from disk.
    """
    global _config_instance
    if _config_instance is None or reload:
        _config_instance = Config()
    return _config_instance
