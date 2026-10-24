"""Parse the ``secrets.wincred`` config section.

Hermes-free on purpose: this half is unit-tested on any platform, and the plugin never
raises on malformed user configuration.
"""

from __future__ import annotations

import re
from typing import Any

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SCHEME = "wincred://"


def parse_map(cfg: Any) -> tuple[dict[str, str], list[str]]:
    """Return ``({ENV_VAR: credential target}, warnings)`` from a raw config section.

    Every malformed entry is skipped with a human-readable warning; nothing here raises.
    Values may be a bare target name or carry the ``wincred://`` scheme.
    """
    warnings: list[str] = []
    if not isinstance(cfg, dict):
        return {}, ["secrets.wincred is not a mapping; nothing to resolve"]

    raw_map = cfg.get("map")
    if raw_map is None:
        return {}, ["secrets.wincred.map is not set; nothing to resolve"]
    if not isinstance(raw_map, dict):
        return {}, ["secrets.wincred.map must be a mapping of ENV_VAR to credential target"]

    mapping: dict[str, str] = {}
    for name, ref in raw_map.items():
        if not isinstance(name, str) or not _ENV_NAME.match(name):
            warnings.append(f"skipping {name!r}: not a valid environment variable name")
            continue
        target = _target(ref)
        if target is None:
            warnings.append(f"skipping {name}: credential reference must be a non-empty string")
            continue
        mapping[name] = target
    return mapping, warnings


def _target(ref: Any) -> str | None:
    if not isinstance(ref, str):
        return None
    target = ref.strip()
    if target[: len(_SCHEME)].lower() == _SCHEME:
        target = target[len(_SCHEME):].strip()
    return target or None
