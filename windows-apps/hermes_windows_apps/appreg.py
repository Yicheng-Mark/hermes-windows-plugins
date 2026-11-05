"""The registry layer of installed software: the four Uninstall keys.

Why registry and not WMI: ``Win32_Product`` only sees MSI packages, reconfigures
them while enumerating (a documented, repair-triggering side effect), and costs
a PowerShell spawn per query. The Uninstall keys are where ``Apps & Features``
itself reads from: four opens cover every source it lists -- the machine's
64-bit and 32-bit views plus the user's -- with no installer touched and no
elevation needed to read.

Layout facts the sweep relies on, all measured on a real machine:

- one subkey per program under each Uninstall key, named by product id or GUID;
- every field is a value inside that subkey; ``EstimatedSize`` is a DWORD in
  kilobytes, ``SystemComponent`` = 1 marks entries the publisher asked
  ``Apps & Features`` to hide (updates and runtimes often carry it);
- ``UninstallString`` is data the publisher wrote -- this plugin reports it,
  never runs it;
- the 32-bit machine view and the user views may not exist on a given install;
  they come back empty, which is the honest answer, never an error.
"""

from __future__ import annotations

from typing import Any, Callable

try:
    import winreg
except ImportError:  # not Windows: the plugin is Windows-only and says so when asked
    winreg = None

UNINSTALL_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
WOW64_UNINSTALL_PATH = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"

# (hive name, subkey, view label) -- the one sweep both tools read. The order
# is the display order: machine entries before user ones, 64-bit before 32-bit.
UNINSTALL_SOURCES = [
    ("hklm", UNINSTALL_PATH, "machine-64"),
    ("hklm", WOW64_UNINSTALL_PATH, "machine-32"),
    ("hkcu", UNINSTALL_PATH, "user-64"),
    ("hkcu", WOW64_UNINSTALL_PATH, "user-32"),
]

# the values one program subkey can carry; read cheaply, reported verbatim
FIELDS = (
    "DisplayName",
    "DisplayVersion",
    "Publisher",
    "DisplayIcon",
    "InstallDate",
    "EstimatedSize",
    "InstallLocation",
    "SystemComponent",
    "WindowsInstaller",
    "NoModify",
    "NoRepair",
    "NoRemove",
    "ReleaseType",
    "UninstallString",
    "HelpLink",
    "URLInfoAbout",
    "Comments",
)


class RegistryUnavailable(Exception):
    """The installed-software registry exists only on Windows (or could not be opened)."""


def _hive(which: str):
    if winreg is None:
        raise RegistryUnavailable("the installed-software registry exists only on Windows")
    return winreg.HKEY_CURRENT_USER if which == "hkcu" else winreg.HKEY_LOCAL_MACHINE


def _subkeys(which: str, path: str, opener: Callable | None = None) -> list[str]:
    """Every subkey name under one Uninstall key; a key that does not exist is empty."""
    if winreg is None:
        raise RegistryUnavailable("the installed-software registry exists only on Windows")
    open_key = opener or winreg.OpenKey
    names: list[str] = []
    try:
        with open_key(_hive(which), path) as key:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(key, index)
                except OSError:
                    break
                names.append(str(name))
                index += 1
    except OSError:
        return []
    return names


def _field(key, name: str, query=None) -> Any:
    """One value of an open subkey, or None when the publisher did not write it."""
    read = query or winreg.QueryValueEx
    try:
        data, _kind = read(key, name)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return data


def _entry(which: str, path: str, subkey: str, view: str,
           opener: Callable | None = None, query: Callable | None = None) -> dict[str, Any]:
    """One program's facts, tagged with where they came from."""
    if winreg is None:
        raise RegistryUnavailable("the installed-software registry exists only on Windows")
    open_key = opener or winreg.OpenKey
    try:
        with open_key(_hive(which), path + "\\" + subkey) as key:
            facts = {field.lower(): _field(key, field, query) for field in FIELDS}
    except OSError:
        return {"subkey": subkey, "view": view, "unreadable": True}
    facts.update({"subkey": subkey, "view": view})
    return facts


def app_entries(opener: Callable | None = None, query: Callable | None = None) -> list[dict[str, Any]]:
    """Every program subkey across the four Uninstall keys, tagged with its view.

    A subkey an unelevated read cannot open stays in the list, flagged, rather
    than silently shrinking the inventory -- security software writes such keys.
    """
    entries: list[dict[str, Any]] = []
    for which, path, view in UNINSTALL_SOURCES:
        for subkey in _subkeys(which, path, opener):
            entries.append(_entry(which, path, subkey, view, opener, query))
    return entries
