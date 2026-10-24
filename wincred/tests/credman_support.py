"""Test-only writer/deleter for generic credentials.

The shipped package is read-only on purpose; these helpers exist so the live test can
seed a uniquely named credential and remove it afterwards.
"""

import ctypes
import os


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2

_API = None


def _api():
    global _API
    if _API is not None:
        return _API
    if os.name != "nt":
        raise RuntimeError("Windows Credential Manager is only available on Windows")

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
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wt.DWORD]
    advapi32.CredWriteW.restype = wt.BOOL
    advapi32.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
    advapi32.CredDeleteW.restype = wt.BOOL
    _API = (advapi32, CREDENTIALW)
    return _API


def write_generic(target: str, secret: bytes, username: str = "hermes-wincred-test") -> None:
    advapi32, credential_type = _api()
    buffer = (ctypes.c_ubyte * len(secret)).from_buffer_copy(secret) if secret else None
    credential = credential_type()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.UserName = username
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.CredentialBlobSize = len(secret)
    credential.CredentialBlob = (
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)) if buffer else None
    )
    if not advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise OSError(ctypes.get_last_error(), f"CredWriteW failed for {target!r}")
    # Keep the buffer alive until after the call has returned.
    del buffer


def delete_generic(target: str) -> None:
    advapi32, _ = _api()
    if not advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        raise OSError(ctypes.get_last_error(), f"CredDeleteW failed for {target!r}")
