"""``wincred`` secret source — the current user's Windows Credential Manager.

Config::

    secrets:
      wincred:
        enabled: true
        map:
          ZAI_API_KEY: hermes/zai          # or wincred://hermes/zai
          OPENAI_API_KEY: hermes/openai

Each mapped value is the *target name* of a generic credential. Values are read at
startup and handed to the orchestrator, which applies them to the environment with the
usual precedence and provenance rules; this source never writes ``os.environ`` itself.
"""

from __future__ import annotations

from pathlib import Path

from agent.secret_sources.base import ErrorKind, FetchResult, SecretSource

from . import credman
from .config import parse_map


class WinCredSource(SecretSource):
    """Resolve environment variables from the current user's generic credentials."""

    name = "wincred"
    label = "Windows Credential Manager"
    shape = "mapped"
    scheme = "wincred"
    remediation_hints = {
        ErrorKind.NOT_CONFIGURED: "Set secrets.wincred.map in config.yaml to an ENV_VAR: "
                                  "credential-target mapping.",
        ErrorKind.BINARY_MISSING: "Windows Credential Manager is only available on Windows.",
        ErrorKind.EMPTY_VALUE: "Check the target names with `cmdkey /list` and store each "
                               "secret as a generic credential.",
        ErrorKind.INTERNAL: "Run `cmdkey /list` and re-check the mapped target names.",
    }

    def config_schema(self) -> dict:
        return {
            "enabled": {
                "type": "bool",
                "default": False,
                "description": "Master switch for the wincred secret source",
            },
            "map": {
                "type": "dict",
                "default": {},
                "description": "Environment variable name -> generic-credential target",
            },
            "timeout_seconds": {
                "type": "number",
                "default": 120,
                "description": "Wall-clock budget for one fetch (local reads are instant)",
            },
        }

    def fetch(self, cfg: dict, home_path: Path) -> FetchResult:
        try:
            return self._fetch(cfg, home_path)
        except Exception as exc:  # contract: fetch() never raises
            return FetchResult().fail(
                f"wincred fetch failed unexpectedly ({type(exc).__name__})",
                ErrorKind.INTERNAL,
            )

    def _fetch(self, cfg: dict, home_path: Path) -> FetchResult:
        result = FetchResult()
        if not isinstance(cfg, dict):
            return result.fail("secrets.wincred is not a mapping", ErrorKind.NOT_CONFIGURED)

        mapping, warnings = parse_map(cfg)
        result.warnings.extend(warnings)
        if not mapping:
            return result.fail(
                "No credentials are mapped; set secrets.wincred.map "
                "(ENV_VAR: credential target).",
                ErrorKind.NOT_CONFIGURED,
            )
        if not credman.available():
            return result.fail(
                "Windows Credential Manager is only available on Windows.",
                ErrorKind.BINARY_MISSING,
            )

        for env_name, target in mapping.items():
            try:
                raw = credman.read_generic(target)
            except credman.CredManUnavailable as exc:
                return result.fail(str(exc), ErrorKind.BINARY_MISSING)
            except credman.CredManError as exc:
                result.warnings.append(_read_failure(env_name, target, exc))
                continue
            except Exception as exc:  # never raise out of fetch()
                result.warnings.append(
                    f"{env_name}: credential read failed unexpectedly ({type(exc).__name__})"
                )
                continue

            try:
                value = credman.decode_secret(raw)
            except credman.CredentialDecodeError:
                result.warnings.append(
                    f"{env_name}: credential {target!r} is not UTF-8 or UTF-16 text"
                )
                continue
            if not value:
                result.warnings.append(f"{env_name}: credential {target!r} is empty")
                continue
            result.secrets[env_name] = value

        if not result.secrets:
            result.error = "No mapped credential could be read from Windows Credential Manager."
            result.error_kind = ErrorKind.EMPTY_VALUE
        return result


def _read_failure(env_name: str, target: str, exc: credman.CredManError) -> str:
    if exc.code == credman.ERROR_NOT_FOUND:
        return f"{env_name}: no generic credential named {target!r}"
    if exc.code == credman.ERROR_NO_SUCH_LOGON_SESSION:
        return f"{env_name}: the current logon session has no credential vault ({target!r})"
    if exc.code == credman.ERROR_ACCESS_DENIED:
        return f"{env_name}: access denied reading {target!r}"
    return f"{env_name}: CredReadW failed for {target!r} (winerror {exc.code})"
