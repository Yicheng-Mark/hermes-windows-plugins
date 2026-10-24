"""Provisioning CLI for the DPAPI secret store.

Hermes only ever *reads* the store. Creating and editing it is a deliberate,
interactive act by the user::

    python -m hermes_dpapi_secrets set OPENAI_API_KEY     # value from a prompt or stdin
    python -m hermes_dpapi_secrets list                   # names only, never values
    python -m hermes_dpapi_secrets unset OPENAI_API_KEY
    python -m hermes_dpapi_secrets path                   # where the store lives

Values are never echoed, never passed on the command line (where they would land
in shell history and the process table) and never written in plaintext.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from . import dpapi, store

DEFAULT_STORE = "secrets.dpapi"


def hermes_home() -> Path:
    """Mirror Hermes' own home resolution: ``HERMES_HOME`` or ``~/.hermes``."""
    override = os.environ.get("HERMES_HOME", "").strip()
    if override:
        return Path(os.path.expanduser(override))
    return Path.home() / ".hermes"


def default_store_path() -> Path:
    return hermes_home() / DEFAULT_STORE


def _read_value() -> str:
    """Read the secret from a hidden prompt, or from stdin when piped."""
    if sys.stdin is not None and sys.stdin.isatty():
        return getpass.getpass("value: ")
    data = sys.stdin.read() if sys.stdin is not None else ""
    return data[:-1] if data.endswith("\n") else data


def _load(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return store.read_store(path)


def cmd_set(args: argparse.Namespace) -> int:
    value = _read_value()
    if not value:
        print("refusing to store an empty value", file=sys.stderr)
        return 1
    if "\x00" in value:
        print("value contains a NUL byte and cannot be an environment variable",
              file=sys.stderr)
        return 1
    path = Path(args.file)
    values = _load(path)
    values[args.name] = value
    store.write_store(path, values)
    print(f"stored {args.name} in {path} ({len(values)} entries)")
    return 0


def cmd_unset(args: argparse.Namespace) -> int:
    path = Path(args.file)
    values = _load(path)
    if args.name not in values:
        print(f"no entry named {args.name} in {path}", file=sys.stderr)
        return 1
    del values[args.name]
    store.write_store(path, values)
    print(f"removed {args.name} ({len(values)} entries left)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"no store at {path}", file=sys.stderr)
        return 1
    for name in store.store_entries(path):
        print(name)
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    print(args.file)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m hermes_dpapi_secrets",
        description="Create and inspect the DPAPI-encrypted secret store read by the "
                    "Hermes `dpapi` secret source.",
    )
    parser.add_argument(
        "--file",
        default=str(default_store_path()),
        help="store path (default: %(default)s)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    set_parser = sub.add_parser("set", help="store a value (read from a prompt or stdin)")
    set_parser.add_argument("name", help="entry name referenced from secrets.dpapi.map")
    set_parser.set_defaults(handler=cmd_set)

    unset_parser = sub.add_parser("unset", help="remove an entry")
    unset_parser.add_argument("name")
    unset_parser.set_defaults(handler=cmd_unset)

    list_parser = sub.add_parser("list", help="list entry names (never values)")
    list_parser.set_defaults(handler=cmd_list)

    path_parser = sub.add_parser("path", help="print the store path")
    path_parser.set_defaults(handler=cmd_path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not dpapi.available():
        print("the DPAPI secret store is only available on Windows", file=sys.stderr)
        return 1
    try:
        return args.handler(args)
    except dpapi.DpapiError as exc:
        print(f"{exc} — the store was written by a different Windows user", file=sys.stderr)
        return 1
    except store.StoreFormatError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
