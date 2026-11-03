"""The registry half of autostart: Run keys, RunOnce, and Explorer's approval records.

Why registry and not WMI: ``Win32_StartupCommand`` misses Explorer's enabled/disabled
state entirely (the ``StartupApproved`` blobs), reads only a fixed source list, and costs
a PowerShell spawn per query. The Run keys and the approval records are three opens each
and answer everything the Startup tab of Task Manager shows -- including state
``Win32_StartupCommand`` has no field for.

The ``StartupApproved`` layout is 12 bytes: a DWORD whose low byte carries the state
Explorer wrote, then a FILETIME of when the person last changed it. The low byte is
``02`` or ``03`` for an enabled entry, ``06`` or ``07`` for one switched off in Task
Manager; other values appear in the wild (a record left behind by an uninstalled
program reads ``01`` on this machine), and are reported as unknown rather than guessed.
"""

from __future__ import annotations

import struct
from typing import Any, Callable

try:
    import winreg
except ImportError:  # not Windows: the plugin is Windows-only and says so when asked
    winreg = None

RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUNONCE_PATH = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
WOW64_RUN_PATH = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
WOW64_RUNONCE_PATH = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce"
APPROVED_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
SHELL_FOLDERS_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"

ENABLED_BYTES = {2, 3}
DISABLED_BYTES = {6, 7}


class RegistryUnavailable(Exception):
    """The autostart registry exists only on Windows (or the hive could not be opened)."""


# (hive name, subkey, source label, scope) -- the one sweep both tools read
RUN_SOURCES = [
    ("hkcu", RUN_PATH, "registry-hkcu-run", "user"),
    ("hkcu", RUNONCE_PATH, "registry-hkcu-runonce", "user"),
    ("hklm", RUN_PATH, "registry-hklm-run", "machine"),
    ("hklm", RUNONCE_PATH, "registry-hklm-runonce", "machine"),
    ("hklm", WOW64_RUN_PATH, "registry-hklm-run-32", "machine"),
    ("hklm", WOW64_RUNONCE_PATH, "registry-hklm-runonce-32", "machine"),
]

APPROVED_SOURCES = [
    ("hkcu", APPROVED_PATH + r"\Run", "registry-hkcu-run"),
    ("hkcu", APPROVED_PATH + r"\RunOnce", "registry-hkcu-runonce"),
    ("hkcu", APPROVED_PATH + r"\StartupFolder", "folder-user"),
    ("hklm", APPROVED_PATH + r"\Run", "registry-hklm-run"),
    ("hklm", APPROVED_PATH + r"\RunOnce", "registry-hklm-runonce"),
    ("hklm", APPROVED_PATH + r"\StartupFolder", "folder-common"),
]


def _hive(which: str):
    if winreg is None:
        raise RegistryUnavailable("the autostart registry exists only on Windows")
    return winreg.HKEY_CURRENT_USER if which == "hkcu" else winreg.HKEY_LOCAL_MACHINE


def _open(which: str, path: str, opener: Callable | None = None):
    open_key = opener or winreg.OpenKey
    return open_key(_hive(which), path)


def _values(which: str, path: str, opener: Callable | None = None) -> dict[str, Any]:
    """Every value of one key, as {name: data}; a key that does not exist is empty."""
    if winreg is None:
        raise RegistryUnavailable("the autostart registry exists only on Windows")
    out: dict[str, Any] = {}
    try:
        with _open(which, path, opener) as key:
            index = 0
            while True:
                try:
                    name, data, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                out[str(name)] = data
                index += 1
    except OSError:
        return {}
    return out


def run_entries(opener: Callable | None = None) -> list[dict[str, Any]]:
    """Every Run/RunOnce value across the six keys, tagged with its source and scope.

    The WOW64 keys sit under WOW6432Node only on 64-bit Windows; on 32-bit installs
    they simply do not exist and come back empty, which is the honest answer.
    """
    entries: list[dict[str, Any]] = []
    for which, path, source, scope in RUN_SOURCES:
        for name, data in _values(which, path, opener).items():
            entries.append(
                {
                    "name": name,
                    "command": str(data) if data is not None else "",
                    "source": source,
                    "scope": scope,
                }
            )
    return entries


def _decode_approval(blob: bytes) -> dict[str, Any]:
    state = "enabled" if blob[0] in ENABLED_BYTES else (
        "disabled" if blob[0] in DISABLED_BYTES else f"unknown (state byte {blob[0]})"
    )
    changed = None
    if len(blob) >= 12:
        stamp = struct.unpack("<Q", blob[4:12])[0]
        if stamp:
            from datetime import datetime, timezone

            changed = datetime.fromtimestamp(stamp / 1e7 - 11644473600, tz=timezone.utc).isoformat()
    return {"state": state, "changed": changed}


def approvals(opener: Callable | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """Explorer's enabled/disabled verdicts, as {(source label, entry name): facts}.

    A record whose Run value is gone (the program was uninstalled and left its
    approval behind) stays in this map; the tools report those separately as orphans.
    """
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for which, path, source in APPROVED_SOURCES:
        for name, data in _values(which, path, opener).items():
            if isinstance(data, bytes) and data:
                out[(source, str(name))] = _decode_approval(data)
    return out


def shell_folder(value_name: str, default: str, which: str = "hkcu", opener: Callable | None = None) -> str:
    """One directory Explorer actually uses, OneDrive redirects included.

    ``Startup`` lives under the user's ``User Shell Folders`` (where a OneDrive
    redirect shows up as a ``%USERPROFILE%\\OneDrive\\...`` value) and
    ``Common Startup`` under the machine's; both are REG_EXPAND_SZ, so the answer
    needs expanding, and the default covers a machine that never set one.
    """
    import os

    raw = _values(which, SHELL_FOLDERS_PATH, opener).get(value_name)
    text = str(raw) if raw else default
    return os.path.expandvars(os.path.expanduser(text))
