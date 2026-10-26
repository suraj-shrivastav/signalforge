"""Vertical configuration loader.

Reads ``verticals/<name>.yaml`` from the package via importlib.resources so the
config ships with the code and can be overridden by dropping a file next to it.
"""

from importlib import resources
from typing import Any

import yaml

PACKAGE = "signalforge.verticals"


class ConfigurationError(Exception):
    """Raised when a vertical config cannot be loaded or is malformed."""


def load_vertical(name: str = "ai_engineering") -> dict[str, Any]:
    """Return the parsed vertical config dict for ``name``."""
    try:
        ref = resources.files(PACKAGE).joinpath(f"{name}.yaml")
        with ref.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise ConfigurationError(f"vertical config not found: {name}.yaml") from exc


def source_enabled(cfg: dict[str, Any], name: str) -> bool:
    """Whether the vertical config leaves ``name`` on (a source absent from it stays on)."""
    return bool(((cfg.get("sources") or {}).get(name) or {}).get("enabled", True))
