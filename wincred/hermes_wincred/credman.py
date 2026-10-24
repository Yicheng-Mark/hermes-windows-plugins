"""Read-only binding to the Windows Credential Manager (advapi32 via ctypes).

The shipped surface is deliberately read-only: this plugin resolves secrets into
environment variables at startup, so it never creates, updates or deletes credentials,
never spawns a process and never touches the network. The test fixtures that need to
seed a credential carry their own writer in ``tests/``, outside the installed package.
"""

from __future__ import annotations

import codecs
import ctypes
import os
from typing import Optional

CRED_TYPE_GENERIC = 1

ERROR_ACCESS_DENIED = 5
ERROR_NOT_FOUND = 1168
ERROR_NO_SUCH_LOGON_SESSION = 1312

_API: Optional[tuple] = None


class CredManUnavailable(RuntimeError):
    """The Credential Manager API cannot be reached on this platform."""


class CredManError(RuntimeError):
    """A ``CredReadW`` call failed; ``code`` is the Win32 error."""

    def __init__(self, target: str, code: int) -> None:
        super().__init__(f"CredReadW failed for {target!r} (winerror {code})")
        self.target = target
        self.code = code


class CredentialDecodeError(ValueError):
    """The credential blob does not decode to text."""


def available() -> bool:
    """Cheap platform gate. Never loads a DLL (``is_available``-style callers)."""
    return os.name == "nt"


def _api():
    """Load advapi32 and declare the structures/signatures once per process."""
    global _API
    if _API is not None:
        return _API
    if not available():
        raise CredManUnavailable("Windows Credential Manager is only available on Windows")

    import ctypes.wintypes as wt

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wt.DWORD),
            ("Type", wt.DWORD),
            ("TargetName", wt.LPWSTR),
            ("Comment", wt.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wt.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wt.DWORD),
            ("AttributeCount", wt.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wt.LPWSTR),
            ("UserName", wt.LPWSTR),
        ]

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.CredReadW.argtypes = [
        wt.LPCWSTR,
        wt.DWORD,
        wt.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    advapi32.CredReadW.restype = wt.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    advapi32.CredFree.restype = None

    _API = (advapi32, CREDENTIALW)
    return _API


def read_generic(target: str) -> bytes:
    """Return the blob of the generic credential named ``target``.

    Raises :class:`CredManUnavailable` off Windows and :class:`CredManError` with the
    Win32 error code when the read fails (``ERROR_NOT_FOUND`` means no such credential).
    """
    advapi32, credential_type = _api()
    pointer = ctypes.POINTER(credential_type)()
    if not advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        raise CredManError(target, ctypes.get_last_error())
    try:
        credential = pointer.contents
        size = int(credential.CredentialBlobSize)
        if size <= 0:
            return b""
        return ctypes.string_at(credential.CredentialBlob, size)
    finally:
        advapi32.CredFree(pointer)


def decode_secret(raw: bytes) -> str:
    """Decode a generic-credential blob into text.

    Windows stores the blob as bytes with no declared encoding. ``cmdkey``, the
    Credential UI and PowerShell write UTF-16LE; most CLI tools write UTF-8. Accept
    both and fail closed on anything else — a mangled API key is worse than no key.
    """
    if not raw:
        return ""
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        try:
            text = raw.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise CredentialDecodeError("credential blob is not valid UTF-16") from exc
        return text.rstrip("\x00")

    text = None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if text is not None:
        clean = text.rstrip("\x00")
        if "\x00" not in clean:
            return clean

    # A UTF-16LE blob of ASCII also decodes as UTF-8 — it just carries a NUL between
    # every character. Those NULs make the value unusable as an env var, so prefer the
    # UTF-16 reading when the byte pattern actually looks like UTF-16 (about half the
    # bytes are NUL), not for a lone trailing NUL on a UTF-8 value.
    if len(raw) % 2 == 0 and (text is None or raw.count(0) >= max(2, len(raw) * 2 // 5)):
        try:
            utf16 = raw.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            utf16 = None
        if utf16 is not None and "\x00" not in utf16 and _plausible_text(utf16):
            return utf16
    # Interior NULs cannot be represented in an environment variable: fail closed rather
    # than hand Hermes a mangled key.
    raise CredentialDecodeError("credential blob is neither UTF-8 nor UTF-16LE")


def _plausible_text(text: str) -> bool:
    """Reject UTF-16 readings full of C0 control characters (binary, not a secret)."""
    return all(ch >= " " or ch in "\t\n\r" for ch in text)
