"""A Hermes terminal environment that runs commands inside an existing WSL distro.

There is no object to create and none to tear down: ``wsl.exe -d <distro>`` starts the
distro on demand and it keeps running afterwards, which is what makes this backend cheap.
One ``bash -c`` spawn per command, and Hermes' own plumbing — command wrapping, cwd tracking,
stdin, timeouts — comes from :class:`BaseEnvironment`. ``wsl.exe`` runs that bash with the
distro's default user, in the distro's own filesystem, over the same files the Windows side
sees at ``/mnt/<drive>``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from tools.environments.base import BaseEnvironment, EnvironmentConnectionError
# The in-tree spawn-per-call backends use this pair too (see tools/environments/ssh.py): it
# owns the Windows no-console-window flags and the utf-8 pipe setup, and bash_argv is the
# shared ``bash [-l] -c <script>`` tail every backend sends.
from tools.environments.base_output import _popen_bash
from tools.environments.remote_common import bash_argv

from . import wsl
from .config import DEFAULT_MOUNT_ROOT, to_posix_path

logger = logging.getLogger(__name__)

#: ``wslpath`` is one CLI call per distro, and the answer cannot change while a session runs.
#: Keyed by (exe, distro) so two Hermes profiles pointing at different distros stay apart.
_mount_root_cache: dict[tuple[str, str], str] = {}
_mount_root_lock = threading.Lock()


def _cached_mount_root(exe: str, distro: str) -> str:
    key = (exe, distro)
    with _mount_root_lock:
        cached = _mount_root_cache.get(key)
    if cached is not None:
        return cached
    try:
        root = wsl.mount_root(exe, distro)
    except Exception:
        logger.debug("WSL: wslpath probe failed for %s; assuming %s", distro, DEFAULT_MOUNT_ROOT,
                     exc_info=True)
        root = DEFAULT_MOUNT_ROOT
    with _mount_root_lock:
        _mount_root_cache[key] = root
    return root


class WslEnvironment(BaseEnvironment):
    """Run commands inside an existing WSL distro on this Windows host."""

    # A stopped distro boots on the first call; the snapshot bootstrap rides that same call.
    _snapshot_timeout = 60
    _stdin_mode = "pipe"
    # The core can pre-empt its password-prompt path for backends whose user is root inside a
    # sandbox (``BaseEnvironment._sudo_nopasswd_works``). A distro has a normal user and a
    # normal sudo, so the switch is deliberately left alone.

    def __init__(self, *, exe: str, distro: str, cwd: str = "~", timeout: int = 60,
                 user: Optional[str] = None, mount_root: Optional[str] = None):
        # Assigned before super() so a failing constructor still has a safe cleanup()/__del__.
        self._closed = True
        self._lock = threading.RLock()
        self._exe = exe
        self._distro = distro
        self._user = (user or "").strip() or None
        self._mount_root = mount_root if mount_root is not None else _cached_mount_root(exe, distro)
        super().__init__(cwd=to_posix_path(cwd, mount_root=self._mount_root), timeout=timeout)
        self._closed = False
        try:
            self.init_session()
        except Exception:
            self.cleanup()
            raise

    # --- identity ------------------------------------------------------------

    @property
    def distro(self) -> str:
        return self._distro

    @property
    def executable(self) -> str:
        return self._exe

    def translate(self, host_path: str) -> str:
        """Host path -> the path this distro sees (public so tests can pin the rule)."""
        return to_posix_path(host_path, mount_root=self._mount_root)

    # --- execution -----------------------------------------------------------

    def execute(self, command: str, cwd: str = "", **kwargs: Any) -> dict:
        """Translate a per-call cwd before handing the command to the base class.

        The base class only sees Linux paths after the first command (its cwd tracking reads
        them out of the shell), but the terminal tool can pass a fresh host path at any time.
        """
        if isinstance(cwd, str) and cwd:
            cwd = self.translate(cwd)
        result = super().execute(command, cwd=cwd, **kwargs)
        # The provider guide documents exit_code; the core reads returncode. Publish both.
        if "returncode" in result:
            result.setdefault("exit_code", result["returncode"])
        return result

    def _wrap_command(self, command: str, cwd: str) -> str:
        """Rewrite the trailing cwd marker so a ``cd`` survives to the next command.

        The stock marker reads ``printf ... "$(pwd -P)"``. Under WSL, a forked-but-not-exec'd
        child — which is what a command substitution is — is handed the directory ``wsl.exe``
        started in, not the shell's current one, so the substitution keeps reporting the
        session's first directory and Hermes never sees a ``cd`` take effect. An external
        binary does inherit the real cwd (``/bin/pwd -P | tr -d '\\n'``, both coreutils), so the
        marker is emitted as three commands that need no subshell. See VALIDATION.md for the
        measurements.

        If a future Hermes changes the marker's shape the replacement simply does not apply and
        the stock behaviour returns — degraded, not broken.
        """
        script = super()._wrap_command(command, cwd)
        marker = self._cwd_marker
        stock = f"printf '\\n{marker}%s{marker}\\n' \"$(pwd -P)\""
        if stock not in script:
            logger.debug("WSL: cwd marker shape changed upstream; keeping the stock marker")
            return script
        rewritten = (f"printf '\\n{marker}'; /bin/pwd -P | tr -d '\\n'; printf '{marker}\\n'")
        return script.replace(stock, rewritten)

    def _run_bash(self, cmd_string: str, *, login: bool = False, timeout: int = 120,
                  stdin_data: Optional[str] = None):
        if self._closed:
            raise EnvironmentConnectionError(f"WSL environment for {self._distro!r} is closed")
        argv = [self._exe, "-d", self._distro]
        if self._user:
            argv.extend(["-u", self._user])
        # ``--`` ends wsl.exe's own option parsing; everything after it is the Linux command.
        argv.append("--")
        argv.extend(bash_argv(cmd_string, login))
        return _popen_bash(argv, stdin_data)

    # --- teardown ------------------------------------------------------------

    def cleanup(self) -> None:
        """Nothing to release: the distro belongs to the user, not to this environment.

        Deliberately does not stop the distro — the user's other shells, services and containers
        share it, and Hermes stopping it on teardown would be a surprise in the middle of their
        work.
        """
        if not hasattr(self, "_lock"):
            return
        with self._lock:
            self._closed = True
