r"""Windows certificate stores through crypt32, read-only, via ctypes.

``CertOpenStore`` with ``CERT_STORE_READONLY_FLAG`` walks a system store's
certificates in-process - no ``certutil`` (whose output follows the display
language), no PowerShell, no network. Facts come straight off each
``CERT_CONTEXT``: the subject and issuer through ``CertGetNameStringW``, the
thumbprint and the friendly name through ``CertGetCertificateContextProperty``,
the enhanced-key-usage list through ``CertGetEnhancedKeyUsage``. Everything a
context owns is copied out into plain Python data before the enumerator moves
on, because the next ``CertEnumCertificatesInStore`` call frees the previous
context.

Every prototype is declared with explicit ``argtypes``/``restype``: on a 64-bit
host an undeclared pointer argument is truncated to 32 bits and the call fails
silently. The DLL loads lazily inside ``_api()`` and nothing platform-specific
is touched at import time, so the module imports on any OS.
"""

from __future__ import annotations

import ctypes
import os
from typing import Any, Dict, List, Optional

CERT_STORE_PROV_SYSTEM_W = 10
CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
CERT_SYSTEM_STORE_LOCAL_MACHINE = 0x00020000
CERT_STORE_READONLY_FLAG = 0x00008000

CERT_NAME_SIMPLE_DISPLAY_TYPE = 4
CERT_NAME_ISSUER_FLAG = 0x1

CERT_SHA1_HASH_PROP_ID = 3
CERT_FRIENDLY_NAME_PROP_ID = 11

CRYPT_E_NOT_FOUND = 0x80092004

DEFAULT_STORES = ("MY", "Root", "CA")
CONTEXT_FLAGS = {
    "user": CERT_SYSTEM_STORE_CURRENT_USER,
    "machine": CERT_SYSTEM_STORE_LOCAL_MACHINE,
}

_EPOCH_OFFSET = 116444736000000000  # FILETIME (100 ns ticks) -> Unix epoch

_API: Optional[tuple] = None


class CertstoreError(RuntimeError):
    """A certificate store could not be opened or walked."""


def available() -> bool:
    """Cheap platform gate. Never loads a DLL."""
    return os.name == "nt"


def filetime_to_epoch(low: int, high: int) -> Optional[float]:
    """FILETIME to a Unix epoch float; ``None`` when the value is the zero stamp."""
    raw = (high << 32) | low
    if raw <= 0:
        return None
    return (raw - _EPOCH_OFFSET) / 10_000_000


def _api():
    """Load crypt32 and declare the structures and signatures once."""
    global _API
    if _API is not None:
        return _API
    if not available():
        raise CertstoreError("the Windows certificate stores are only readable on Windows")

    import ctypes.wintypes as wt

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    class ALGORITHM_IDENTIFIER(ctypes.Structure):
        _fields_ = [("pszObjId", ctypes.c_char_p), ("Parameters", DATA_BLOB)]

    class BIT_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wt.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
            ("cUnusedBits", wt.DWORD),
        ]

    class PUBLIC_KEY_INFO(ctypes.Structure):
        _fields_ = [("Algorithm", ALGORITHM_IDENTIFIER), ("PublicKey", BIT_BLOB)]

    class EXTENSION(ctypes.Structure):
        _fields_ = [("pszObjId", ctypes.c_char_p), ("fCritical", wt.BOOL), ("Value", DATA_BLOB)]

    class CERT_INFO(ctypes.Structure):
        # field order and nesting follow wincrypt.h - Subject sits AFTER the
        # two FILETIMEs there; ctypes pads to native alignment, so no offset
        # is ever written by hand
        _fields_ = [
            ("dwVersion", wt.DWORD),
            ("SerialNumber", DATA_BLOB),
            ("SignatureAlgorithm", ALGORITHM_IDENTIFIER),
            ("Issuer", DATA_BLOB),
            ("NotBefore", FILETIME),
            ("NotAfter", FILETIME),
            ("Subject", DATA_BLOB),
            ("SubjectPublicKeyInfo", PUBLIC_KEY_INFO),
            ("IssuerUniqueId", BIT_BLOB),
            ("SubjectUniqueId", BIT_BLOB),
            ("cExtension", wt.DWORD),
            ("rgExtension", ctypes.POINTER(EXTENSION)),
        ]

    class CERT_CONTEXT(ctypes.Structure):
        _fields_ = [
            ("dwCertEncodingType", wt.DWORD),
            ("pbCertEncoded", ctypes.POINTER(ctypes.c_char)),
            ("cbCertEncoded", wt.DWORD),
            ("pCertInfo", ctypes.POINTER(CERT_INFO)),
            ("hCertStore", ctypes.c_void_p),
        ]

    class ENHKEY_USAGE(ctypes.Structure):
        _fields_ = [
            ("cUsageIdentifier", wt.DWORD),
            ("rgpszUsageIdentifier", ctypes.POINTER(ctypes.c_char_p)),
        ]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)

    # the provider constant 10 travels as a pointer-sized integer cast to LPCSTR
    crypt32.CertOpenStore.argtypes = [
        ctypes.c_void_p,   # lpszStoreProvider
        wt.DWORD,          # dwEncodingType
        ctypes.c_void_p,   # hCryptProv (legacy, NULL)
        wt.DWORD,          # dwFlags
        wt.LPCWSTR,        # pvPara: the store name, wide for provider 10
    ]
    crypt32.CertOpenStore.restype = ctypes.c_void_p

    crypt32.CertEnumCertificatesInStore.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    crypt32.CertEnumCertificatesInStore.restype = ctypes.POINTER(CERT_CONTEXT)

    crypt32.CertFreeCertificateContext.argtypes = [ctypes.c_void_p]
    crypt32.CertFreeCertificateContext.restype = wt.BOOL

    crypt32.CertCloseStore.argtypes = [ctypes.c_void_p, wt.DWORD]
    crypt32.CertCloseStore.restype = wt.BOOL

    crypt32.CertGetNameStringW.argtypes = [
        ctypes.c_void_p,   # pCertContext
        wt.DWORD,          # dwType
        wt.DWORD,          # dwFlags
        ctypes.c_void_p,   # pvTypePara
        ctypes.c_void_p,   # pszNameString (NULL to size)
        wt.DWORD,          # cchNameString
    ]
    crypt32.CertGetNameStringW.restype = wt.DWORD

    crypt32.CertGetCertificateContextProperty.argtypes = [
        ctypes.c_void_p,             # pCertContext
        wt.DWORD,                    # dwPropId
        ctypes.c_void_p,             # pvData
        ctypes.POINTER(wt.DWORD),    # pcbData
    ]
    crypt32.CertGetCertificateContextProperty.restype = wt.BOOL

    crypt32.CertGetEnhancedKeyUsage.argtypes = [
        ctypes.c_void_p,             # pCertContext
        wt.DWORD,                    # dwFlags
        ctypes.c_void_p,             # pUsage
        ctypes.POINTER(wt.DWORD),    # pcbUsage
    ]
    crypt32.CertGetEnhancedKeyUsage.restype = wt.BOOL

    _API = (crypt32, CERT_INFO, CERT_CONTEXT, ENHKEY_USAGE)
    return _API


def _name_of(crypt32, ctx: int, flags: int) -> Optional[str]:
    """One name string off a context: the subject, or the issuer with the flag."""
    size = crypt32.CertGetNameStringW(ctx, CERT_NAME_SIMPLE_DISPLAY_TYPE, flags, None, None, 0)
    if size <= 1:  # zero, or the lone terminator of an empty name
        return None
    buffer = ctypes.create_unicode_buffer(size)
    copied = crypt32.CertGetNameStringW(
        ctx, CERT_NAME_SIMPLE_DISPLAY_TYPE, flags, None, buffer, size
    )
    return buffer.value if copied else None


def _thumbprint_of(crypt32, ctx: int) -> Optional[str]:
    size = ctypes.c_ulong(0)
    ok = crypt32.CertGetCertificateContextProperty(
        ctx, CERT_SHA1_HASH_PROP_ID, None, ctypes.byref(size)
    )
    if not ok or not 1 <= size.value <= 64:
        return None
    raw = ctypes.create_string_buffer(size.value)
    ok = crypt32.CertGetCertificateContextProperty(
        ctx, CERT_SHA1_HASH_PROP_ID, raw, ctypes.byref(size)
    )
    if not ok:
        return None
    return ctypes.string_at(raw, size.value).hex().upper()


def _friendly_of(crypt32, ctx: int) -> Optional[str]:
    size = ctypes.c_ulong(0)
    ok = crypt32.CertGetCertificateContextProperty(
        ctx, CERT_FRIENDLY_NAME_PROP_ID, None, ctypes.byref(size)
    )
    if not ok or size.value < 2:  # absent, or zero terminator only
        return None
    raw = ctypes.create_string_buffer(size.value)
    ok = crypt32.CertGetCertificateContextProperty(
        ctx, CERT_FRIENDLY_NAME_PROP_ID, raw, ctypes.byref(size)
    )
    return raw.raw.decode("utf-16-le", "replace").split("\x00", 1)[0] or None if ok else None


def _eku_of(crypt32, enhkey_usage, ctx: int) -> Optional[List[str]]:
    """The EKU extension's OIDs; ``None`` when the certificate carries none."""
    size = ctypes.c_ulong(0)
    ok = crypt32.CertGetEnhancedKeyUsage(ctx, 0, None, ctypes.byref(size))
    if not ok:
        # CRYPT_E_NOT_FOUND: no EKU extension at all - the certificate does not
        # restrict its purposes, which is itself the answer
        return None
    if size.value < 4:
        return []
    buffer = ctypes.create_string_buffer(size.value)
    ok = crypt32.CertGetEnhancedKeyUsage(ctx, 0, buffer, ctypes.byref(size))
    if not ok:
        raise CertstoreError("the enhanced key usage could not be read a second time")
    usage = ctypes.cast(buffer, ctypes.POINTER(enhkey_usage)).contents
    count = min(usage.cUsageIdentifier, 256)  # a guard, not an expectation
    oids = []
    for i in range(count):
        item = usage.rgpszUsageIdentifier[i]
        if item:
            oids.append(item.decode("ascii", "replace"))
    return oids


def _facts(enhkey_usage, contents) -> Dict[str, Any]:
    """Copy every fact this plugin reports off one live CERT_CONTEXT."""
    crypt32, info = contents.crypt32, contents.info
    raw_subject = ctypes.string_at(info.Subject.pbData, info.Subject.cbData) if info.Subject.pbData else b""
    raw_issuer = ctypes.string_at(info.Issuer.pbData, info.Issuer.cbData) if info.Issuer.pbData else b""
    serial = ctypes.string_at(info.SerialNumber.pbData, info.SerialNumber.cbData) if info.SerialNumber.pbData else b""
    big_endian = serial[::-1].lstrip(b"\x00") or serial[::-1]
    key = info.SubjectPublicKeyInfo
    return {
        "subject": _name_of(crypt32, contents.address, 0),
        "issuer": _name_of(crypt32, contents.address, CERT_NAME_ISSUER_FLAG),
        "self_signed": bool(raw_subject) and raw_subject == raw_issuer,
        "serial_hex": big_endian.hex().upper() if serial else None,
        "thumbprint": _thumbprint_of(crypt32, contents.address),
        "friendly_name": _friendly_of(crypt32, contents.address),
        "not_before": filetime_to_epoch(
            info.NotBefore.dwLowDateTime, info.NotBefore.dwHighDateTime
        ),
        "not_after": filetime_to_epoch(
            info.NotAfter.dwLowDateTime, info.NotAfter.dwHighDateTime
        ),
        "signature_oid": key_algo_oid(info.SignatureAlgorithm.pszObjId),
        "public_key": {
            "algorithm_oid": key_algo_oid(key.Algorithm.pszObjId),
            "raw_size": key.PublicKey.cbData,
            "key_bytes": ctypes.string_at(
                key.PublicKey.pbData, key.PublicKey.cbData
            ) if key.PublicKey.pbData and key.PublicKey.cbData <= 4096 else b"",
            "parameters": ctypes.string_at(
                key.Algorithm.Parameters.pbData, key.Algorithm.Parameters.cbData
            ) if key.Algorithm.Parameters.pbData and key.Algorithm.Parameters.cbData <= 4096 else b"",
        },
        "eku_oids": _eku_of(crypt32, enhkey_usage, contents.address),
        "version": int(info.dwVersion) + 1,
    }


def key_algo_oid(psz: Optional[bytes]) -> Optional[str]:
    return psz.decode("ascii", "replace") if psz else None


class _Live:
    """What a live enumeration hands the fact collector: the address and the struct."""

    def __init__(self, crypt32, pointer) -> None:
        self.crypt32 = crypt32
        self.address = ctypes.cast(pointer, ctypes.c_void_p).value
        self.info = pointer.contents.pCertInfo.contents


def iter_certs(contexts=("user", "machine"), stores=DEFAULT_STORES) -> List[Dict[str, Any]]:
    """Every certificate in the given contexts' stores, fully copied out.

    Raises :class:`CertstoreError` on non-Windows platforms and when a store
    cannot be opened at all; a store that opens but holds nothing is fine.
    """
    crypt32, cert_info_t, cert_context_t, enhkey_usage = _api()

    rows: List[Dict[str, Any]] = []
    for context in contexts:
        flags = CONTEXT_FLAGS.get(context)
        if flags is None:
            continue
        for store in stores:
            handle = crypt32.CertOpenStore(
                ctypes.c_void_p(CERT_STORE_PROV_SYSTEM_W), 0, None,
                flags | CERT_STORE_READONLY_FLAG, str(store),
            )
            if not handle:
                # the readonly open is refused for stores this account cannot see
                continue
            try:
                # the enumerator frees the previous context itself; the last one
                # is freed by the call that returns NULL, so the loop needs no
                # manual free - and no fact may be read after the next call
                prev = ctypes.c_void_p(None)
                while True:
                    ctx = crypt32.CertEnumCertificatesInStore(handle, prev)
                    if not ctx:
                        break
                    try:
                        row = _facts(enhkey_usage, _Live(crypt32, ctx))
                    finally:
                        prev = ctypes.cast(ctx, ctypes.c_void_p)
                    row["context"] = context
                    row["store"] = store
                    rows.append(row)
            finally:
                crypt32.CertCloseStore(handle, 0)
    return rows


__all__ = [
    "CertstoreError",
    "available",
    "filetime_to_epoch",
    "iter_certs",
    "DEFAULT_STORES",
]
