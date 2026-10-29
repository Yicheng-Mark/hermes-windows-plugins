"""The registry half of a service's registration: dependencies, delayed start, failure actions.

Why the registry and not the CIM: ``Win32_Service.DependOnService`` exists as a property but
is never populated (a listing of 293 services on Windows 11 returned none, while ``sc qc``
and the registry both show them), and failure actions live nowhere in CIM at all — only in
the ``FailureActions`` binary value, whose layout is the 32-bit ``SERVICE_FAILURE_ACTIONS``
ABI: ``ResetPeriod`` (DWORD, seconds), two DWORD string offsets (non-zero only when a message
or a command is configured), ``cActions`` (DWORD), a DWORD offset to the action array (20 in
practice), then ``cActions`` pairs of ``type`` (DWORD) and ``delay`` (DWORD, milliseconds).
Verified against ``wuauserv``, whose blob decodes to three "restart after 60 s" actions —
exactly the default the Services snap-in shows.
"""

from __future__ import annotations

import struct
from typing import Callable

try:
    import winreg
except ImportError:  # not Windows: the plugin is Windows-only and says so when asked
    winreg = None

SERVICES_KEY = r"SYSTEM\CurrentControlSet\Services"

_GROUP = "+"  # a dependency naming a load-order group rather than a service

ACTION_NAMES = {
    0: "nothing",
    1: "restart the service",
    2: "restart the computer",
    3: "run a command",
}


class RegistryUnavailable(Exception):
    """The services registry exists only on Windows (or the hive could not be opened)."""


def _value(name: str, value_name: str, opener: Callable | None = None):
    """One registry value of one service, or None when the service does not set it."""
    if winreg is None:
        raise RegistryUnavailable("the services registry exists only on Windows")
    open_key = opener or winreg.OpenKey
    try:
        with open_key(winreg.HKEY_LOCAL_MACHINE, f"{SERVICES_KEY}\\{name}") as key:
            value, _kind = winreg.QueryValueEx(key, value_name)
            return value
    except OSError:
        return None


def depends_on(name: str, opener: Callable = winreg.OpenKey) -> list[str]:
    """The services and groups this one waits for, '+' prefixed when it names a group."""
    raw = _value(name, "DependOnService", opener)
    if not raw:
        return []
    items = [str(item).strip() for item in raw if str(item).strip()]
    return [item[1:] + " (group)" if item.startswith(_GROUP) else item for item in items]


def delayed_start(name: str, opener: Callable = winreg.OpenKey) -> bool:
    """Whether an Automatic service waits a minute after boot before starting."""
    return _value(name, "DelayedAutostart", opener) == 1


def _actions(blob: bytes) -> list[dict]:
    """The action array out of a FailureActions blob."""
    try:
        reset, _reboot_msg, _command, count, actions_at = struct.unpack_from("<5I", blob, 0)
    except struct.error:
        return []
    actions = []
    for index in range(count):
        try:
            action_type, delay_ms = struct.unpack_from("<2I", blob, actions_at + 8 * index)
        except struct.error:
            break
        actions.append(
            {
                "type": ACTION_NAMES.get(action_type, f"unknown ({action_type})"),
                "after_seconds": round(delay_ms / 1000, 1),
            }
        )
    return actions


def failure_policy(name: str, opener: Callable = winreg.OpenKey) -> dict | None:
    """What Windows does when this service fails, and when it forgets the failures."""
    blob = _value(name, "FailureActions", opener)
    if not blob:
        return None
    if isinstance(blob, list):  # winreg yields bytes; a list only appears in tests
        blob = bytes(blob)
    reset, _reboot_msg, _command, count, _actions_at = struct.unpack_from("<5I", blob, 0)
    policy = {
        "actions": _actions(blob),
        "count": count,
    }
    policy["reset_after_hours"] = round(reset / 3600, 1) if reset else None
    return policy
