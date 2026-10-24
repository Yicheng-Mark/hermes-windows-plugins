"""``dpapi`` secret source — an encrypted secret file keyed by the Windows profile.

Config::

    secrets:
      dpapi:
        enabled: true
        file: secrets.dpapi          # relative to the Hermes home; this is the default
        map:
          ZAI_API_KEY: zai           # or dpapi://zai
          OPENAI_API_KEY: openai

The file holds one DPAPI-encrypted blob (see :mod:`hermes_dpapi_secrets.store`).
Values are decrypted at startup and handed to the orchestrator, which applies
them with the usual precedence and provenance rules; this source never writes
``os.environ`` itself and never touches the file for writing.
"""

from __future__ import annotations

from pathlib import Path

from agent.secret_sources.base import ErrorKind, FetchResult, SecretSource

from . import dpapi, store
from .config import parse_map, store_path


class DpapiSecretsSource(SecretSource):
    """Resolve environment variables from a DPAPI-encrypted secret file."""

    name = "dpapi"
    label = "Windows DPAPI secret file"
    shape = "mapped"
    scheme = "dpapi"
    remediation_hints = {
        ErrorKind.NOT_CONFIGURED: "Create the store with `python -m hermes_dpapi_secrets "
                                  "set NAME` (on Windows, as the same user that runs "
                                  "Hermes) and map ENV_VAR to that name in "
                                  "secrets.dpapi.map.",
        ErrorKind.BINARY_MISSING: "Windows DPAPI is only available on Windows.",
        ErrorKind.AUTH_FAILED: "The store cannot be decrypted by this Windows user. "
                               "Re-create it with `python -m hermes_dpapi_secrets set NAME` "
                               "as the account that runs Hermes.",
        ErrorKind.EMPTY_VALUE: "List the store with `python -m hermes_dpapi_secrets list` "
                               "and check that every mapped name exists.",
    }

    def config_schema(self) -> dict:
        return {
            "enabled": {
                "type": "bool",
                "default": False,
                "description": "Master switch for the dpapi secret source",
            },
            "file": {
                "type": "str",
                "default": "secrets.dpapi",
                "description": "Store path, relative to the Hermes home directory",
            },
            "map": {
                "type": "dict",
                "default": {},
                "description": "Environment variable name -> name inside the store",
            },
            "timeout_seconds": {
                "type": "number",
                "default": 120,
                "description": "Wall-clock budget for one fetch (local decryption is instant)",
            },
        }

    def fetch(self, cfg: dict, home_path: Path) -> FetchResult:
        try:
            return self._fetch(cfg, home_path)
        except Exception as exc:  # contract: fetch() never raises
            return FetchResult().fail(
                f"dpapi fetch failed unexpectedly ({type(exc).__name__})",
                ErrorKind.INTERNAL,
            )

    def _fetch(self, cfg: dict, home_path: Path) -> FetchResult:
        result = FetchResult()
        if not isinstance(cfg, dict):
            return result.fail("secrets.dpapi is not a mapping", ErrorKind.NOT_CONFIGURED)

        mapping, warnings = parse_map(cfg)
        result.warnings.extend(warnings)
        if not mapping:
            return result.fail(
                "No variables are mapped; set secrets.dpapi.map (ENV_VAR: store name).",
                ErrorKind.NOT_CONFIGURED,
            )

        path = store_path(cfg, home_path)
        if not path.is_file():
            return result.fail(
                f"Secret store {str(path)!r} does not exist.", ErrorKind.NOT_CONFIGURED
            )
        if not dpapi.available():
            return result.fail(
                "Windows DPAPI is only available on Windows.", ErrorKind.BINARY_MISSING
            )

        try:
            values = store.read_store(path)
        except dpapi.DpapiUnavailable as exc:
            return result.fail(str(exc), ErrorKind.BINARY_MISSING)
        except dpapi.DpapiError as exc:
            return result.fail(
                f"{exc} — {path} was written by a different Windows user or profile, "
                "or the file is corrupt.",
                ErrorKind.AUTH_FAILED,
            )
        except store.StoreFormatError as exc:
            return result.fail(str(exc), ErrorKind.NOT_CONFIGURED)
        except OSError as exc:
            return result.fail(f"cannot read {path}: {exc}", ErrorKind.INTERNAL)

        for env_name, entry in mapping.items():
            if entry not in values:
                result.warnings.append(f"{env_name}: no entry named {entry!r} in the store")
                continue
            value = values[entry]
            if not value:
                result.warnings.append(f"{env_name}: entry {entry!r} is empty")
                continue
            result.secrets[env_name] = value

        if not result.secrets:
            result.error = "No mapped entry could be read from the DPAPI secret store."
            result.error_kind = ErrorKind.EMPTY_VALUE
        return result
