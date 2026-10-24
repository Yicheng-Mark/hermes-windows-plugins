"""The on-disk secret file: a DPAPI blob holding a flat ``{name: value}`` map.

Layout::

    HERMES-DPAPI-1\\n<DPAPI blob>

The magic prefix is not security — DPAPI already refuses a blob it did not
produce — it turns "this is some other file" into a clear error instead of an
opaque decryption failure. Writes go to a temporary file in the same directory
and are moved into place with ``os.replace``, so an interrupted write can never
leave a truncated store behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping

from . import dpapi

MAGIC = b"HERMES-DPAPI-1\n"


class StoreFormatError(ValueError):
    """The file is not a store this plugin wrote."""


def read_store(path: Path) -> dict[str, str]:
    """Decrypt and parse the store at ``path``.

    Raises :class:`StoreFormatError` for a file that is not ours,
    :class:`dpapi.DpapiError` when this user cannot decrypt it (another account
    wrote it, the profile changed, or the blob is corrupt) and
    :class:`StoreFormatError` again for a decrypted payload that is not a flat
    string map.
    """
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise StoreFormatError(
            f"{path} is not a Hermes DPAPI secret store (missing header)"
        )
    blob = data[len(MAGIC):]
    if not blob:
        raise StoreFormatError(f"{path} has a header but no encrypted payload")

    plain = dpapi.unprotect(blob)
    try:
        parsed = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise StoreFormatError(f"{path} decrypted to something that is not JSON") from exc
    if not isinstance(parsed, dict):
        raise StoreFormatError(f"{path} does not hold a name -> value mapping")
    values: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise StoreFormatError(f"{path} holds a non-string entry ({key!r})")
        values[key] = value
    return values


def write_store(path: Path, values: Mapping[str, str]) -> None:
    """Encrypt ``values`` into ``path``, replacing any existing store atomically."""
    target = Path(path)
    plain = json.dumps(dict(values), ensure_ascii=False, sort_keys=True).encode("utf-8")
    data = MAGIC + dpapi.protect(plain)

    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def store_entries(path: Path) -> list[str]:
    """Names present in the store — never the values."""
    return sorted(read_store(path))
