"""Read-only process-table access through kernel32.

``CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS)`` returns the rows Task Manager reads: PID,
parent PID, image name and thread count. Per process, ``QueryFullProcessImageName`` adds the
full image path and ``GetProcessTimes`` adds the creation time — the pair that turns "parent
PID 4592" into "this child's parent is gone, the PID now belongs to something newer".

Nothing here opens a process for anything but read, writes nothing, and starts no child
process. Processes the account may not open (System, Idle, other users) come back with no
path and no start time instead of failing the whole call.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any, Dict, List, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH = 260
PATH_BUFFER = 32768

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
FILETIME_EPOCH_OFFSET = 11_644_473_600  # seconds between 1601-01-01 and 1970-01-01


class WinProcError(Exception):
    """A kernel32 call the process table cannot continue without failed."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


_kernel32: Any = None


def _kernel() -> Any:
    """Bind kernel32 once, with every prototype declared.

    On 64-bit the handles are pointers: without an explicit ``restype`` ctypes hands back a
    truncated int and every later call fails with a bogus "invalid handle".
    """
    global _kernel32
    if _kernel32 is not None:
        return _kernel32
    if not IS_WINDOWS:
        raise WinProcError("the process table is only available on Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(FILETIME)] * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32 = kernel32
    return kernel32


def filetime_to_epoch(ticks: int) -> float:
    """Convert a Windows FILETIME (100 ns ticks since 1601) to a Unix epoch timestamp."""
    return ticks / 10_000_000 - FILETIME_EPOCH_OFFSET


def _ticks(filetime: FILETIME) -> int:
    return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime


def snapshot() -> List[Dict[str, Any]]:
    """Every process the snapshot API reports, without opening any of them."""
    kernel32 = _kernel()
    handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if handle == INVALID_HANDLE_VALUE or not handle:
        code = ctypes.get_last_error()
        raise WinProcError(f"CreateToolhelp32Snapshot failed (error {code})", code)
    rows: List[Dict[str, Any]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(handle, ctypes.byref(entry))
        while ok:
            rows.append({
                "pid": int(entry.th32ProcessID),
                "parent_pid": int(entry.th32ParentProcessID),
                "name": entry.szExeFile,
                "threads": int(entry.cntThreads),
            })
            ok = kernel32.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(handle)
    if not rows:
        code = ctypes.get_last_error()
        raise WinProcError(f"the process snapshot came back empty (error {code})", code)
    return rows


def details(pid: int) -> Tuple[Optional[str], Optional[float]]:
    """Image path and creation time for one PID, or ``(None, None)`` when it is not ours to read."""
    kernel32 = _kernel()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None, None
    try:
        path: Optional[str] = None
        buffer = ctypes.create_unicode_buffer(PATH_BUFFER)
        size = wintypes.DWORD(PATH_BUFFER)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            path = buffer.value or None
        started: Optional[float] = None
        created = FILETIME()
        exited = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            started = filetime_to_epoch(_ticks(created))
        return path, started
    finally:
        kernel32.CloseHandle(handle)
