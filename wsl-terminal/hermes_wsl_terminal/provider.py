"""Registration and classification for the ``wsl`` terminal backend.

The provider is what makes ``terminal.backend: wsl`` a first-class selection: the setup
picker, the dashboard probe, ``hermes status``, the system-prompt environment hints and the
approval layer all read these attributes instead of a hardcoded name list. Declaring them
here is what keeps commands that run in a Linux distro from being described to the model as
a Windows shell.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

from agent.terminal_env_provider import TerminalEnvironmentProvider

from . import wsl
from .config import ENV_DISTRO, ENV_USER, resolve_distro

logger = logging.getLogger(__name__)


class WslProvider(TerminalEnvironmentProvider):
    """Run Hermes terminal tools inside an existing WSL distro."""

    name = "wsl"
    display_name = "WSL distro"
    # Commands run in Linux, inside the distro's own filesystem: host OS, home and cwd hints
    # must not reach the prompt.
    is_remote = True
    # But it is not a container: the distro shares this machine's drives at /mnt/<drive>, the
    # project files are the same files, and there is no disposable sandbox to reason about.
    # Keeping this False is what lets the host cwd pass through and be translated, instead of
    # the core substituting a container-side default.
    is_container = False

    @property
    def skip_container_guards(self) -> bool:
        # A distro is the user's real machine, not a throwaway sandbox: destructive-command
        # approval stays on. Explicit rather than inherited, so a future default cannot flip it.
        return False

    @property
    def description(self) -> str:
        return ("Run commands inside an existing WSL distro (bash on Linux), over the same "
                "files Windows sees at /mnt/<drive>.")

    @property
    def env_description(self) -> str:
        return "a Linux shell inside a WSL distro on this Windows host (Windows drives are at /mnt/<drive>)"

    # --- availability --------------------------------------------------------

    def _resolve(self) -> Optional[str]:
        if sys.platform != "win32":
            return None
        try:
            return wsl.resolve_wsl()
        except wsl.WslError:
            return None

    def is_available(self) -> bool:
        """Cheap enough for UI paints: platform and file checks only, no subprocess."""
        return self._resolve() is not None

    def check_requirements(self, config: dict[str, Any]) -> bool:
        if sys.platform != "win32":
            logger.error("The wsl backend runs a WSL distro, which is Windows-only; this host "
                         "reports platform %r.", sys.platform)
            return False
        try:
            exe = wsl.resolve_wsl()
        except wsl.WslError as exc:
            logger.error("wsl backend selected but the CLI was not found: %s", exc)
            return False
        try:
            distros = wsl.list_distros(exe)
        except Exception as exc:
            logger.error("wsl backend selected, but `%s -l -q` failed (%s). Run "
                         "`wsl --install` or `wsl --update`, then retry.", exe, exc)
            return False
        if not distros:
            logger.error("wsl backend selected, but no distro is installed. Install one with "
                         "`wsl --install -d Ubuntu`, then retry.")
            return False
        wanted = (config.get("wsl_distro") or os.environ.get(ENV_DISTRO) or "").strip()
        if wanted and wanted not in distros:
            logger.error("wsl backend selected with distro %r, but this host has: %s",
                         wanted, ", ".join(distros))
            return False
        logger.info("wsl backend ready: %s (distros: %s)", exe, ", ".join(distros))
        return True

    def probe(self) -> tuple[str, str]:
        if sys.platform != "win32":
            return ("unavailable", "A WSL distro is a Windows-only backend.")
        try:
            exe = wsl.resolve_wsl()
        except wsl.WslError as exc:
            return ("needs_setup", str(exc))
        try:
            distros = wsl.list_distros(exe, timeout=5)
        except Exception:
            return ("unavailable", f"{exe} did not answer `-l -q`.")
        if not distros:
            return ("needs_setup", "No distro is installed — `wsl --install -d Ubuntu`.")
        try:
            chosen = resolve_distro(os.environ.get(ENV_DISTRO), distros,
                                    wsl.default_distro(exe, timeout=5))
        except Exception:
            chosen = distros[0]
        return ("ready", f"running in {chosen}")

    def setup_instructions(self) -> list[str]:
        lines = [
            "The wsl backend runs commands in a distro you already have; it does not install one.",
            "Pick the distro with the HERMES_WSL_DISTRO environment variable (default: the "
            "distro `wsl` itself starts with, usually your default one).",
            "Set HERMES_WSL_USER to run as a different user than the distro's default.",
            "Windows drives are visible inside the distro at /mnt/<drive>, so a host path such "
            "as C:\\Users\\me\\proj is translated automatically.",
        ]
        return lines

    def doctor_checks(self) -> list[tuple[bool, str, str]]:
        rows: list[tuple[bool, str, str]] = []
        exe = self._resolve()
        if exe is None:
            detail = ("only available on Windows" if sys.platform != "win32"
                      else "wsl.exe not found — run `wsl --install`")
            return [(False, "WSL backend", detail)]
        rows.append((True, "wsl.exe", exe))
        try:
            reported = wsl.version(exe)
        except Exception:
            reported = ""
        if reported:
            rows.append((True, "WSL version", reported))
        try:
            distros = wsl.list_distros(exe)
        except Exception as exc:
            return rows + [(False, "WSL distros", f"`-l -q` failed: {exc}")]
        if not distros:
            return rows + [(False, "WSL distros", "none installed — `wsl --install -d Ubuntu`")]
        rows.append((True, "WSL distros", ", ".join(distros)))
        try:
            chosen = resolve_distro(os.environ.get(ENV_DISTRO), distros,
                                    wsl.default_distro(exe))
        except Exception:
            chosen = distros[0]
        rows.append((True, "WSL backend distro", f"{chosen} ({ENV_DISTRO} overrides)"))
        return rows

    # --- environment construction -------------------------------------------

    def create_environment(self, *, cwd: str, timeout: int, task_id: str = "default",
                           image: Optional[str] = None, container_config: Optional[dict] = None,
                           **kwargs: Any):
        from .environment import WslEnvironment

        exe = wsl.resolve_wsl()
        distros = wsl.list_distros(exe)
        if not distros:
            raise wsl.WslError("no WSL distro is installed; run `wsl --install -d Ubuntu` first")
        distro = resolve_distro(os.environ.get(ENV_DISTRO), distros, wsl.default_distro(exe))
        user = os.environ.get(ENV_USER) or None
        return WslEnvironment(exe=exe, distro=distro or distros[0], cwd=cwd or "~",
                              timeout=timeout, user=user)
