"""Binding to the Windows Data Protection API (crypt32 via ctypes).

``CryptProtectData`` / ``CryptUnprotectData`` derive the key from the *current
Windows user profile*, so a blob written here is readable by that user on that
machine and by nobody else — including another local account, a copy of the file
moved to a different machine, or the same user after the profile's master keys are
reset.

Every prototype is declared with explicit ``argtypes``/``restype``: on a 64-bit
host an undeclared pointer argument is truncated to 32 bits and the call fails
silently (that is exactly the class of bug this project files fixes for).
"""

from __future__ import annotations

import ctypes
import os
from typing import Optional

# Never pop a UI from a startup path, and never fall back to a weaker key.
CRYPTPROTECT_UI_FORBIDDEN = 0x1

_API: Optional[tuple] = None


class DpapiUnavailable(RuntimeError):
    """The Data Protection API cannot be reached on this platform."""


class DpapiError(RuntimeError):
    """A protect/unprotect call failed; ``code`` is the Win32 error."""

    def __init__(self, operation: str, code: int) -> None:
        super().__init__(f"{operation} failed (winerror {code})")
        self.operation = operation
        self.code = code


def available() -> bool:
    """Cheap platform gate. Never loads a DLL."""
    return os.name == "nt"


def protect(data: bytes) -> bytes:
    """Encrypt ``data`` for the current user. Returns the DPAPI blob."""
    return _transform("CryptProtectData", data)


def unprotect(blob: bytes) -> bytes:
    """Decrypt a blob this user produced. Raises :class:`DpapiError` otherwise."""
    return _transform("CryptUnprotectData", blob)


def _api():
    """Load crypt32/kernel32 and declare the structures and signatures once."""
    global _API
    if _API is not None:
        return _API
    if not available():
        raise DpapiUnavailable("Windows DPAPI is only available on Windows")

    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wt.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    blob_ptr = ctypes.POINTER(DATA_BLOB)
    crypt32.CryptProtectData.argtypes = [
        blob_ptr,                            # pDataIn
        wt.LPCWSTR,                          # szDataDescr
        blob_ptr,                            # pOptionalEntropy
        ctypes.c_void_p,                     # pvReserved
        ctypes.c_void_p,                     # pPromptStruct
        wt.DWORD,                            # dwFlags
        blob_ptr,                            # pDataOut
    ]
    crypt32.CryptProtectData.restype = wt.BOOL
    # The description is an out-parameter here; passing NULL skips it.
    crypt32.CryptUnprotectData.argtypes = [
        blob_ptr,                            # pDataIn
        ctypes.POINTER(wt.LPWSTR),           # ppszDataDescr
        blob_ptr,                            # pOptionalEntropy
        ctypes.c_void_p,                     # pvReserved
        ctypes.c_void_p,                     # pPromptStruct
        wt.DWORD,                            # dwFlags
        blob_ptr,                            # pDataOut
    ]
    crypt32.CryptUnprotectData.restype = wt.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    _API = (crypt32, kernel32, DATA_BLOB)
    return _API


def _transform(operation: str, payload: bytes) -> bytes:
    crypt32, kernel32, data_blob = _api()
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("DPAPI input must be bytes")

    buffer = ctypes.create_string_buffer(bytes(payload), len(payload))
    blob_in = data_blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = data_blob()
    function = getattr(crypt32, operation)

    if operation == "CryptProtectData":
        ok = function(
            ctypes.byref(blob_in), "hermes-dpapi", None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
        )
    else:
        ok = function(
            ctypes.byref(blob_in), None, None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
        )
    if not ok:
        raise DpapiError(operation, ctypes.get_last_error())

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if blob_out.pbData:
            kernel32.LocalFree(blob_out.pbData)
