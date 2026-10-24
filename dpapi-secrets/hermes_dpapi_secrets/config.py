"""Parse the ``secrets.dpapi`` config section.

Hermes-free on purpose: this half is unit-tested on any platform, and nothing
here raises on malformed user configuration — every bad entry becomes a warning.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SCHEME = "dpapi://"
DEFAULT_FILENAME = "secrets.dpapi"


def parse_map(cfg: Any) -> tuple[dict[str, str], list[str]]:
    """Return ``({ENV_VAR: store name}, warnings)`` from a raw config section.

    A mapped value may be a bare store name or carry the ``dpapi://`` prefix.
    """
    warnings: list[str] = []
    if not isinstance(cfg, dict):
        return {}, ["secrets.dpapi is not a mapping; nothing to resolve"]

    raw_map = cfg.get("map")
    if raw_map is None:
        return {}, ["secrets.dpapi.map is not set; nothing to resolve"]
    if not isinstance(raw_map, dict):
        return {}, ["secrets.dpapi.map must be a mapping of ENV_VAR to a store name"]

    mapping: dict[str, str] = {}
    for name, ref in raw_map.items():
        if not isinstance(name, str) or not _ENV_NAME.match(name):
            warnings.append(f"skipping {name!r}: not a valid environment variable name")
            continue
        key = _entry_name(ref)
        if key is None:
            warnings.append(f"skipping {name}: store name must be a non-empty string")
            continue
        mapping[name] = key
    return mapping, warnings


def _entry_name(ref: Any) -> str | None:
    if not isinstance(ref, str):
        return None
    name = ref.strip()
    if name[: len(_SCHEME)].lower() == _SCHEME:
        name = name[len(_SCHEME):].strip()
    return name or None


def store_path(cfg: Any, home_path: Path) -> Path:
    """Resolve ``secrets.dpapi.file`` against the Hermes home directory.

    An unset or unusable value falls back to ``<home>/secrets.dpapi``; a relative
    path is relative to the home directory, and ``~`` is expanded.
    """
    raw = cfg.get("file") if isinstance(cfg, dict) else None
    if isinstance(raw, str) and raw.strip():
        candidate = Path(os.path.expanduser(raw.strip()))
        return candidate if candidate.is_absolute() else Path(home_path) / candidate
    return Path(home_path) / DEFAULT_FILENAME
