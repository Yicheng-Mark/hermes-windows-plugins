"""The folder half of autostart: what sits in the Startup folders."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable

from . import startupreg

SKIP_NAMES = {"desktop.ini"}  # folder customization, not something anyone launches


def scan(path: str, source: str, scope: str, lister: Callable[[str], list[str]] | None = None) -> list[dict[str, Any]]:
    """Every file in one Startup folder as an entry; a folder that cannot be read is empty.

    Windows launches anything in these folders through the shell, so no extension
    filter is applied -- a stray ``.exe`` shows up the same way a ``.lnk`` does.
    """
    try:
        names = lister(path) if lister else sorted(os.listdir(path))
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for name in names:
        if name.lower() in SKIP_NAMES:
            continue
        full = os.path.join(path, name)
        try:
            stat = os.stat(full)
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            size = stat.st_size
        except OSError:
            modified, size = None, None
        entries.append(
            {
                "name": name,
                "command": full,
                "source": source,
                "scope": scope,
                "file": {"path": full, "size": size, "modified": modified},
            }
        )
    return entries


def folders(shell_folder: Callable[..., str]) -> list[dict[str, Any]]:
    """The user's Startup folder and the machine-wide one, redirected paths honored."""
    import os

    user = shell_folder("Startup", os.path.join("%APPDATA%", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"), which="hkcu")
    common = shell_folder(
        "Common Startup",
        os.path.join("%ProgramData%", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"),
        which="hklm",
    )
    return scan(user, "folder-user", "user") + scan(common, "folder-common", "machine")
