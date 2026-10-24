"""``wsl.exe`` calls this backend needs, kept free of Hermes imports.

Only three things are asked of the CLI: which distros exist, where a Windows path lands
inside one, and whether it answers at all. Everything else (starting the distro, running the
command, forwarding stdin) is a single ``wsl.exe -d <distro> -- bash -c`` spawn per command.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .config import (
    DEFAULT_MOUNT_ROOT,
    decode_cli_output,
    mount_root_from_c_drive,
    parse_default_distro,
    parse_distro_list,
)

#: Keep a console window from flashing for every command when Hermes is launched from a GUI.
_CREATE_NO_WINDOW = 0x08000000


class WslError(RuntimeError):
    """Raised when ``wsl.exe`` is missing or refuses a call the backend depends on."""


def resolve_wsl() -> str:
    """Absolute path to ``wsl.exe``.

    PATH first, then the System32 location, because a Hermes started from a shortcut does not
    always inherit the PATH a terminal would.
    """
    if sys.platform != "win32":
        raise WslError(f"WSL is a Windows feature; this host reports platform {sys.platform!r}")
    found = shutil.which("wsl.exe") or shutil.which("wsl")
    if found:
        return found
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    candidate = Path(system_root) / "System32" / "wsl.exe"
    if candidate.is_file():
        return str(candidate)
    raise WslError("wsl.exe was not found: install WSL with `wsl --install`, then reopen the "
                   "terminal so the PATH update is picked up")


def _creation_flags() -> int:
    return _CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run_capture(argv: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Run one CLI call with stdin closed and both streams captured as bytes.

    Bytes, not text: ``wsl.exe`` prints its own messages as UTF-16 (see
    :func:`hermes_wsl_terminal.config.decode_cli_output`) and a text-mode capture would decode
    them with the host code page.
    """
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=_creation_flags(),
            check=False,
        )
    except FileNotFoundError as exc:
        raise WslError(f"{argv[0]!r} could not be started: {exc}") from exc


def list_distros(exe: str, *, timeout: float = 15.0) -> list[str]:
    result = run_capture([exe, "-l", "-q"], timeout=timeout)
    if result.returncode != 0:
        detail = decode_cli_output(result.stderr).strip() or decode_cli_output(result.stdout).strip()
        raise WslError(f"`{exe} -l -q` exited {result.returncode}"
                       + (f": {detail}" if detail else ""))
    return parse_distro_list(decode_cli_output(result.stdout))


def default_distro(exe: str, *, timeout: float = 15.0) -> Optional[str]:
    """The distro ``wsl.exe`` would start with no ``-d``, then the first registered one."""
    result = run_capture([exe, "-l", "-v"], timeout=timeout)
    if result.returncode == 0:
        marked = parse_default_distro(decode_cli_output(result.stdout))
        if marked:
            return marked
    distros = list_distros(exe, timeout=timeout)
    return distros[0] if distros else None


def version(exe: str, *, timeout: float = 15.0) -> str:
    """First line of ``wsl --version``, or "" when this WSL is too old for the flag.

    The line is localized (``WSL 版本: 3.0.3.0`` on a Chinese Windows), so it is reported
    verbatim and never parsed for a version number.
    """
    result = run_capture([exe, "--version"], timeout=timeout)
    if result.returncode != 0:
        return ""
    text = decode_cli_output(result.stdout)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else ""


def to_unix_path(exe: str, distro: str, host_path: str, *, timeout: float = 15.0) -> Optional[str]:
    """Ask the distro itself to translate a path (``wslpath -u``), or None when it cannot.

    The command goes through a shell because ``wsl.exe`` runs whatever follows ``--`` through
    one: a Windows path handed over as a bare argument has its backslashes eaten as escapes
    (``D:\\work`` arrives as ``D:work``). Quoting it is what makes the probe answer for the
    path that was actually asked about.
    """
    command = f"wslpath -u {shlex.quote(host_path)}"
    result = run_capture([exe, "-d", distro, "--", "/bin/sh", "-c", command], timeout=timeout)
    if result.returncode != 0:
        return None
    text = decode_cli_output(result.stdout).strip()
    return text or None


def mount_root(exe: str, distro: str, *, timeout: float = 15.0) -> str:
    """Where Windows drives are mounted in this distro (``/mnt`` unless wsl.conf moved it)."""
    unix_c = to_unix_path(exe, distro, "C:\\", timeout=timeout)
    return mount_root_from_c_drive(unix_c) if unix_c else DEFAULT_MOUNT_ROOT
