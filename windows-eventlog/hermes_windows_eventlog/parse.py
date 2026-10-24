"""Turn Event Log XML into flat, JSON-safe records.

The Event Log renders every record as XML in the
``http://schemas.microsoft.com/win/2004/08/events/event`` namespace. Providers are
free to put their payload in ``EventData`` (named or positional ``Data`` elements),
in ``UserData`` (provider schema), or nowhere at all, so every field here is
optional and parsed defensively.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"

LEVEL_NAMES = {
    1: "critical",
    2: "error",
    3: "warning",
    4: "information",
    5: "verbose",
    0: "log_always",
}

# Exception codes that a Windows crash record can carry, with the name every
# debugger shows for them. Values are matched case-insensitively on the hex form.
EXCEPTION_CODES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC0000006: "IN_PAGE_ERROR",
    0xC0000008: "INVALID_HANDLE",
    0xC0000017: "NO_MEMORY",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000022: "ACCESS_DENIED",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC0000096: "PRIVILEGED_INSTRUCTION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000135: "DLL_NOT_FOUND",
    0xC0000139: "ENTRYPOINT_NOT_FOUND",
    0xC0000142: "DLL_INIT_FAILED",
    0xC000027B: "STOWED_EXCEPTION",
    0xC0000374: "HEAP_CORRUPTION",
    0xC0000409: "STACK_BUFFER_OVERRUN",
    0xC000041D: "UNHANDLED_EXCEPTION",
    0xC0000420: "ASSERTION_FAILURE",
    0xC0000602: "FAIL_FAST_EXCEPTION",
    0x80000003: "BREAKPOINT",
    0x80000004: "SINGLE_STEP",
    0xE0434352: "CLR_EXCEPTION",
    0xE06D7363: "CPP_EXCEPTION",
}

_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$")
_HEX_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{1,8})$")


def parse_time(text: Optional[str]) -> Optional[datetime]:
    """Parse a SystemTime value, tolerating 7-digit fractions and missing zones."""
    if not text:
        return None
    match = _TIME_RE.match(str(text).strip())
    if not match:
        return None
    base, fraction, zone = match.groups()
    stamp = base.replace(" ", "T")
    if fraction:
        stamp += "." + (fraction + "000000")[:6]
    if not zone or zone == "Z":
        stamp += "+00:00"
    elif ":" in zone:
        stamp += zone
    else:
        stamp += f"{zone[:3]}:{zone[3:]}"
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_time(value: Optional[datetime]) -> Optional[str]:
    """Render a time as ISO 8601 with microseconds and a ``Z`` suffix."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def cutoff_from_hours(hours: float) -> datetime:
    return utc_now() - timedelta(hours=hours)


def decode_exception(code: Any) -> Optional[str]:
    """Map a crash exception code to its debugger name, e.g. ``0xC0000005`` -> ACCESS_VIOLATION."""
    if code is None:
        return None
    text = str(code).strip()
    match = _HEX_RE.match(text)
    if not match:
        return None
    value = int(match.group(1), 16)
    return EXCEPTION_CODES.get(value)


def describe_exception(code: Any) -> Optional[str]:
    """``0xC0000005 (ACCESS_VIOLATION)`` when the code is known, else the raw code."""
    if code is None:
        return None
    text = str(code).strip()
    if not text:
        return None
    name = decode_exception(text)
    if name:
        try:
            normalized = "0x%08X" % int(_HEX_RE.match(text).group(1), 16)  # type: ignore[union-attr]
        except Exception:
            normalized = text
        return f"{normalized} ({name})"
    return text


def _text(element: Optional[ET.Element]) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def parse_event(xml_text: str) -> Dict[str, Any]:
    """Parse one rendered event into ``{system..., data, data_list, user_data}``."""
    root = ET.fromstring(xml_text)
    system = root.find(f"{NS}System")
    record: Dict[str, Any] = {
        "time": None,
        "event_id": None,
        "level": None,
        "level_number": None,
        "provider": None,
        "channel": None,
        "computer": None,
        "process_id": None,
        "thread_id": None,
        "record_id": None,
        "data": {},
        "data_list": [],
        "user_data": None,
    }
    if system is not None:
        provider = system.find(f"{NS}Provider")
        created = system.find(f"{NS}TimeCreated")
        execution = system.find(f"{NS}Execution")
        record["provider"] = provider.get("Name") if provider is not None else None
        record["time"] = created.get("SystemTime") if created is not None else None
        if execution is not None:
            record["process_id"] = _as_int(execution.get("ProcessID"))
            record["thread_id"] = _as_int(execution.get("ThreadID"))
        level_number = _as_int(_text(system.find(f"{NS}Level")))
        record["level_number"] = level_number
        record["level"] = LEVEL_NAMES.get(level_number) if level_number is not None else None
        record["event_id"] = _as_int(_text(system.find(f"{NS}EventID")))
        record["channel"] = _text(system.find(f"{NS}Channel")) or None
        record["computer"] = _text(system.find(f"{NS}Computer")) or None
        record["record_id"] = _as_int(_text(system.find(f"{NS}EventRecordID")))

    event_data = root.find(f"{NS}EventData")
    if event_data is not None:
        for index, item in enumerate(event_data.findall(f"{NS}Data")):
            value = _text(item)
            name = item.get("Name")
            if name:
                record["data"][name] = value
            else:
                record["data_list"].append(value)
                record["data"][f"#{index}"] = value

    user_data = root.find(f"{NS}UserData")
    if user_data is not None:
        record["user_data"] = ET.tostring(user_data, encoding="unicode").strip()
    return record


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip(), 10)
    except (TypeError, ValueError):
        return None


def payload_text(record: Dict[str, Any]) -> str:
    """All payload values joined, for substring filtering."""
    parts: List[str] = list(record.get("data_list") or [])
    parts.extend((record.get("data") or {}).values())
    if record.get("user_data"):
        parts.append(record["user_data"])
    return " ".join(part for part in parts if part)


# Keys that name the crashing application, in the order each event kind uses them.
_APP_KEYS = (
    "Application Name",
    "AppName",
    "Application",
    "P1",
    "Process Name",
    "Faulting application name",
    "Image",
)


def field(data: Optional[Dict[str, Any]], *names: str) -> Optional[str]:
    """Case-insensitive named lookup: providers differ in casing across Windows builds."""
    if not data:
        return None
    lowered = {str(key).lower(): value for key, value in data.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return None


def app_name(record: Dict[str, Any]) -> Optional[str]:
    data = record.get("data") or {}
    for key in _APP_KEYS:
        value = (field(data, key) or "").strip()
        if value:
            return value
    return None


def truncate(value: Any, limit: int = 400) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= limit:
        return value
    return value[:limit] + f"... [{len(value) - limit} chars truncated]"
