"""Read-only port/process table access through iphlpapi.dll and kernel32.

``GetExtendedTcpTable`` / ``GetExtendedUdpTable`` return the same table ``netstat -ano``
prints, with the owning PID attached, so a caller gets the answer without parsing
localized console output. The plugin never opens a socket, never binds and never
touches another process beyond ``QueryFullProcessImageName`` (read-only).
"""

from __future__ import annotations

import ctypes
import socket
import sys
from ctypes import wintypes
from typing import Any, Dict, List, Optional

IS_WINDOWS = sys.platform == "win32"

AF_INET = 2
AF_INET6 = 23
TCP_TABLE_OWNER_PID_ALL = 5
UDP_TABLE_OWNER_PID = 1

ERROR_INSUFFICIENT_BUFFER = 122
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

TCP_STATES = {
    1: "closed",
    2: "listen",
    3: "syn_sent",
    4: "syn_received",
    5: "established",
    6: "fin_wait_1",
    7: "fin_wait_2",
    8: "close_wait",
    9: "closing",
    10: "last_ack",
    11: "time_wait",
    12: "delete_tcb",
}

SYSTEM_PIDS = {0: "System Idle Process", 4: "System"}


class WinNetError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        self.code = int(code)
        super().__init__(f"{message} (win32 {self.code})" if self.code else message)


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_TCP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwState", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_UDPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_UDP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class _IpHelpApi:
    def __init__(self) -> None:
        dll = ctypes.WinDLL("iphlpapi", use_last_error=True)
        for name in ("GetExtendedTcpTable", "GetExtendedUdpTable"):
            fn = getattr(dll, name)
            fn.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.DWORD),
                wintypes.BOOL,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
            ]
            fn.restype = wintypes.DWORD
        self.get_tcp_table = dll.GetExtendedTcpTable
        self.get_udp_table = dll.GetExtendedUdpTable

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        query_name = kernel32.QueryFullProcessImageNameW
        query_name.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        query_name.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        self.open_process = open_process
        self.query_process_name = query_name
        self.close_handle = close_handle


_API: Optional[_IpHelpApi] = None
_NAME_CACHE: Dict[int, Optional[str]] = {}


def _api() -> _IpHelpApi:
    global _API
    if _API is None:
        if not IS_WINDOWS:
            raise WinNetError(0, "the port table is only available on Windows")
        try:
            _API = _IpHelpApi()
        except OSError as exc:  # pragma: no cover - Windows always has iphlpapi
            raise WinNetError(0, f"iphlpapi could not be loaded: {exc}") from exc
    return _API


def _fetch(table_class: int, af: int, row_type) -> List[Any]:
    api = _api()
    getter = api.get_tcp_table if table_class == TCP_TABLE_OWNER_PID_ALL else api.get_udp_table
    size = wintypes.DWORD(0)
    code = getter(None, ctypes.byref(size), False, af, table_class, 0)
    if code not in (0, ERROR_INSUFFICIENT_BUFFER):
        raise WinNetError(code, "the table size could not be read")
    if size.value == 0:
        return []
    buffer = ctypes.create_string_buffer(size.value)
    code = getter(buffer, ctypes.byref(size), False, af, table_class, 0)
    if code != 0:
        raise WinNetError(code, "the port table could not be read")
    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    row_size = ctypes.sizeof(row_type)
    raw = buffer.raw
    rows = []
    for index in range(int(count)):
        start = 4 + index * row_size
        chunk = raw[start:start + row_size]
        if len(chunk) < row_size:
            break
        rows.append(row_type.from_buffer_copy(chunk))
    return rows


def _ipv4_text(value: int) -> str:
    return socket.inet_ntoa(int(value).to_bytes(4, "little"))


def _ipv6_text(raw, scope: int = 0) -> str:
    packed = bytes(int(part) for part in raw)
    text = socket.inet_ntop(socket.AF_INET6, packed)
    if scope and text.startswith("fe80"):
        return f"{text}%{int(scope)}"
    return text


def _port(value: int) -> int:
    # The low 16 bits are stored in network byte order.
    return socket.ntohs(int(value) & 0xFFFF)


def tcp_rows(include_ipv6: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in _fetch(TCP_TABLE_OWNER_PID_ALL, AF_INET, MIB_TCPROW_OWNER_PID):
        rows.append({
            "protocol": "tcp",
            "address": _ipv4_text(row.dwLocalAddr),
            "port": _port(row.dwLocalPort),
            "remote_address": _ipv4_text(row.dwRemoteAddr),
            "remote_port": _port(row.dwRemotePort),
            "state": TCP_STATES.get(int(row.dwState), str(row.dwState)),
            "pid": int(row.dwOwningPid),
        })
    if include_ipv6:
        for row in _fetch(TCP_TABLE_OWNER_PID_ALL, AF_INET6, MIB_TCP6ROW_OWNER_PID):
            rows.append({
                "protocol": "tcp6",
                "address": _ipv6_text(row.ucLocalAddr, row.dwLocalScopeId),
                "port": _port(row.dwLocalPort),
                "remote_address": _ipv6_text(row.ucRemoteAddr, row.dwRemoteScopeId),
                "remote_port": _port(row.dwRemotePort),
                "state": TCP_STATES.get(int(row.dwState), str(row.dwState)),
                "pid": int(row.dwOwningPid),
            })
    return rows


def udp_rows(include_ipv6: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in _fetch(UDP_TABLE_OWNER_PID, AF_INET, MIB_UDPROW_OWNER_PID):
        rows.append({
            "protocol": "udp",
            "address": _ipv4_text(row.dwLocalAddr),
            "port": _port(row.dwLocalPort),
            "remote_address": None,
            "remote_port": None,
            "state": "bound",
            "pid": int(row.dwOwningPid),
        })
    if include_ipv6:
        for row in _fetch(UDP_TABLE_OWNER_PID, AF_INET6, MIB_UDP6ROW_OWNER_PID):
            rows.append({
                "protocol": "udp6",
                "address": _ipv6_text(row.ucLocalAddr, row.dwLocalScopeId),
                "port": _port(row.dwLocalPort),
                "remote_address": None,
                "remote_port": None,
                "state": "bound",
                "pid": int(row.dwOwningPid),
            })
    return rows


def process_name(pid: int) -> Optional[str]:
    """Image name for *pid* via QueryFullProcessImageName (read-only, no injection)."""
    if pid in SYSTEM_PIDS:
        return SYSTEM_PIDS[pid]
    if pid in _NAME_CACHE:
        return _NAME_CACHE[pid]
    name: Optional[str] = None
    api = _api()
    handle = api.open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if api.query_process_name(handle, 0, buffer, ctypes.byref(size)):
                name = buffer.value or None
        finally:
            api.close_handle(handle)
    _NAME_CACHE[pid] = name
    return name
