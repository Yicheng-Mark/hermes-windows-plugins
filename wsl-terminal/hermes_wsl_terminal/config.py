"""Path and settings rules for the ``wsl`` terminal backend.

Hermes-free on purpose: the translation rules are the part a reviewer will want to check
(what a Windows path becomes inside the distro, which distro a session lands in), and
keeping them out of the Hermes-importing modules means they are provable without a Hermes
install.
"""

from __future__ import annotations

import re
from typing import Optional

#: Where WSL automounts Windows drives by default. A distro can move it in ``/etc/wsl.conf``,
#: so the environment asks ``wslpath`` once and passes the real value in; this is the fallback.
DEFAULT_MOUNT_ROOT = "/mnt"

#: Optional overrides. Both are ordinary host environment variables, read fresh per
#: environment so a single Hermes install can drive more than one distro.
ENV_DISTRO = "HERMES_WSL_DISTRO"
ENV_USER = "HERMES_WSL_USER"
ENV_MOUNT_ROOT = "HERMES_WSL_MOUNT_ROOT"

#: ``C:\Users\me`` / ``C:/Users/me`` / ``C:`` — the drive letter is the whole parse.
_DRIVE_RE = re.compile(r"^(?P<drive>[A-Za-z]):(?P<rest>.*)$", re.DOTALL)

#: UNC shares that address a distro's own filesystem rather than a network server.
_WSL_UNC_SHARES = ("wsl$", "wsl.localhost")


def to_posix_path(host_path: str, *, mount_root: str = DEFAULT_MOUNT_ROOT) -> str:
    """Translate a host path into the path the distro sees.

    Four shapes reach this function and each has one correct answer:

    * a Windows path — ``C:\\Users\\me\\proj`` becomes ``/mnt/c/Users/me/proj``, using the
      mount root the distro actually configured rather than a hardcoded ``/mnt``;
    * a UNC path into the distro — ``\\\\wsl.localhost\\Ubuntu\\home\\me`` becomes
      ``/home/me`` (``\\\\wsl$\\...`` is the same share under its other name);
    * a path the model already wrote the Linux way — returned untouched;
    * nothing, ``~`` or a relative path — returned untouched so ``cd`` and the shell keep
      resolving it exactly as they would in a terminal.

    A UNC share that is *not* a distro share is returned unchanged: this backend cannot
    reach a network share from inside the distro, and silently rewriting it would move the
    command to a path that does not exist.
    """
    text = (host_path or "").strip()
    if not text or text == "~" or text == "~/":
        return "~"
    if text.startswith("~/"):
        return text

    normalized = text.replace("\\", "/")
    if normalized.startswith("//"):
        parts = [part for part in normalized.split("/") if part]
        if parts and parts[0].lower() in _WSL_UNC_SHARES:
            # //wsl$/Distro/path or //wsl.localhost/Distro/path: the first two segments are
            # the share and the distro name, and neither exists inside the filesystem.
            rest = parts[2:]
            return "/" + "/".join(rest) if rest else "/"
        return normalized
    if normalized.startswith("/"):
        return normalized

    match = _DRIVE_RE.match(normalized)
    if match:
        drive = match.group("drive").lower()
        rest = match.group("rest").strip("/")
        base = mount_root.rstrip("/")
        return f"{base}/{drive}/{rest}" if rest else f"{base}/{drive}"
    return normalized


def mount_root_from_c_drive(unix_c_drive: str) -> str:
    """Derive the automount root from ``wslpath -u 'C:\\'`` (``/mnt/c/`` -> ``/mnt``).

    A distro can mount drives at any prefix; asking the distro is the only way to know.
    Anything unexpected falls back to the default rather than producing a path that cannot
    resolve.
    """
    text = (unix_c_drive or "").strip()
    if not text.startswith("/"):
        return DEFAULT_MOUNT_ROOT
    trimmed = text.rstrip("/")
    if trimmed == "/c":
        return ""
    if trimmed.endswith("/c"):
        return trimmed[:-2]
    return DEFAULT_MOUNT_ROOT


def parse_distro_list(text: str) -> list[str]:
    """Distro names from ``wsl.exe -l -q``, one per line and nothing else."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def parse_default_distro(text: str) -> Optional[str]:
    """The ``*``-marked name from ``wsl.exe -l -v``, or None when the table has no marker."""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("*"):
            continue
        columns = stripped.lstrip("*").strip().split()
        if columns:
            return columns[0]
    return None


def decode_cli_output(raw: bytes) -> str:
    """Decode output from ``wsl.exe`` itself.

    The two halves of this CLI print in different encodings: ``-l``/``--version``/``--status``
    (wsl.exe's own messages) are UTF-16LE even when stdout is redirected, while anything the
    Linux side writes is UTF-8. Detect the UTF-16 shape instead of trusting the host code
    page — a Chinese or Japanese Windows would otherwise decode the distro list into mojibake.
    """
    if not raw:
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    # UTF-16LE without a BOM: every ASCII byte is followed by a NUL. Half of a plain UTF-8
    # ASCII string never looks like this, and non-ASCII UTF-8 has no NUL bytes at all.
    if len(raw) >= 4 and raw[1::2].count(0) >= max(1, len(raw) // 4):
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def resolve_distro(explicit: Optional[str], available: list[str], default: Optional[str] = None) -> Optional[str]:
    """Which distro a session runs in: explicit choice, then the distro's own default, then
    the first registered one. None when the host has no distro at all."""
    name = (explicit or "").strip()
    if name:
        return name
    if default:
        return default
    return available[0] if available else None
