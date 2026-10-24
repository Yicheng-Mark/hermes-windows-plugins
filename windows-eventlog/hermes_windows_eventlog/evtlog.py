"""Read-only access to the Windows Event Log through wevtapi.dll.

Only four entry points are used -- ``EvtQuery``, ``EvtNext``, ``EvtRender`` and
``EvtClose``. The plugin never writes to a log, never opens a remote session and
never spawns a child process.

``wevtapi`` is loaded lazily so the module imports (and the plugin registers) on
platforms that have no Event Log at all; every call then fails with a structured
:class:`EventLogError` instead of an ImportError.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Iterator, List, Optional

IS_WINDOWS = sys.platform == "win32"

EVT_QUERY_CHANNEL_PATH = 0x0001
EVT_QUERY_REVERSE_DIRECTION = 0x0200
EVT_RENDER_EVENT_XML = 0x0001

ERROR_ACCESS_DENIED = 5
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259
ERROR_TIMEOUT = 1460

# EvtNext pulls handles in batches; the timeout is how long the API waits for a
# slow provider to deliver the next batch.
_NEXT_BATCH = 16
_NEXT_TIMEOUT_MS = 1000
# A rendered event XML is a few KB; refuse to grow the buffer past this instead of
# trying to allocate whatever a corrupt size field asks for.
_MAX_XML_BYTES = 4 * 1024 * 1024
_INITIAL_XML_BYTES = 8192

_ERROR_TEXT = {
    2: "the system cannot find the file specified",
    5: "access denied (this channel needs elevation)",
    87: "invalid parameter",
    122: "buffer too small",
    1460: "timed out waiting for the log to answer",
    15000: "invalid channel path",
    15001: "invalid query",
    15003: "the query is not valid for this channel",
    15005: "the query result is not available",
    15007: "channel not found",
    15008: "the event is no longer available",
    15011: "the query result is stale",
}


class EventLogError(RuntimeError):
    """A failed Event Log call, with the Win32 error code attached."""

    def __init__(self, code: int, message: str, detail: str = "") -> None:
        self.code = int(code)
        self.detail = detail
        base = message or _ERROR_TEXT.get(self.code, "Event Log call failed")
        super().__init__(f"{base} (win32 {self.code})" if self.code else base)


class _EvtApi:
    """ctypes surface of wevtapi.dll, loaded once per process."""

    def __init__(self) -> None:
        dll = ctypes.WinDLL("wevtapi", use_last_error=True)

        query = dll.EvtQuery
        query.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        query.restype = wintypes.HANDLE

        next_ = dll.EvtNext
        next_.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        next_.restype = wintypes.BOOL

        render = dll.EvtRender
        render.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        render.restype = wintypes.BOOL

        close = dll.EvtClose
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL

        self.query = query
        self.next = next_
        self.render = render
        self.close = close


_API: Optional[_EvtApi] = None


def _api() -> _EvtApi:
    global _API
    if _API is None:
        if not IS_WINDOWS:
            raise EventLogError(
                0,
                "the Windows Event Log is only available on Windows",
                f"this interpreter runs on {sys.platform}",
            )
        try:
            _API = _EvtApi()
        except OSError as exc:  # pragma: no cover - Windows always has wevtapi
            raise EventLogError(0, "wevtapi.dll could not be loaded", str(exc)) from exc
    return _API


def _render_xml(api: _EvtApi, event: int) -> str:
    size = _INITIAL_XML_BYTES
    used = wintypes.DWORD(0)
    properties = wintypes.DWORD(0)
    while size <= _MAX_XML_BYTES:
        buffer = ctypes.create_string_buffer(size)
        ok = api.render(
            None,
            event,
            EVT_RENDER_EVENT_XML,
            size,
            ctypes.cast(buffer, ctypes.c_void_p),
            ctypes.byref(used),
            ctypes.byref(properties),
        )
        if ok:
            raw = buffer.raw[: used.value]
            return raw.decode("utf-16-le", "replace").rstrip("\x00")
        code = ctypes.get_last_error()
        if code != ERROR_INSUFFICIENT_BUFFER:
            raise EventLogError(code, "the event could not be rendered")
        # `used` reports the required size in bytes, always bigger than `size` here.
        size = max(used.value, size * 2)
    raise EventLogError(0, "the event XML is larger than the plugin will render")


def iter_events(channel: str, xpath: str, limit: int) -> Iterator[str]:
    """Yield up to *limit* events from *channel*, newest first, as XML strings.

    *xpath* is an Event Log XPath filter (``*`` selects everything). Results are
    read in reverse (newest first) so a caller that stops early on an old event
    never walks the whole log; the query handle is closed when iteration ends.
    """
    api = _api()
    handle = api.query(
        None, channel, xpath or "*", EVT_QUERY_CHANNEL_PATH | EVT_QUERY_REVERSE_DIRECTION
    )
    if not handle:
        code = ctypes.get_last_error()
        raise EventLogError(code, f"could not query {channel!r}: {_ERROR_TEXT.get(code, 'query failed')}")
    delivered = 0
    try:
        batch = (wintypes.HANDLE * _NEXT_BATCH)()
        while delivered < limit:
            returned = wintypes.DWORD(0)
            ok = api.next(
                handle, _NEXT_BATCH, batch, _NEXT_TIMEOUT_MS, 0, ctypes.byref(returned)
            )
            if not ok:
                code = ctypes.get_last_error()
                if code == ERROR_NO_MORE_ITEMS:
                    return
                if code == ERROR_TIMEOUT:
                    continue
                raise EventLogError(code, f"reading {channel!r} failed")
            if returned.value == 0:
                return
            for index in range(returned.value):
                handle_event = batch[index]
                try:
                    yield _render_xml(api, handle_event)
                finally:
                    api.close(handle_event)
                delivered += 1
                if delivered >= limit:
                    return
    finally:
        api.close(handle)


def query(channel: str, xpath: str, limit: int) -> List[str]:
    """List form of :func:`iter_events`, for tests and small probes."""
    return list(iter_events(channel, xpath, limit))
