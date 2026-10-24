"""Tool handlers: crash forensics and structured Event Log queries.

Every handler returns a JSON string, never raises, and accepts ``**kwargs`` for the
context Hermes injects. The Windows calls themselves live in :mod:`.evtlog`; this
module only shapes queries and summarises results.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import evtlog
from .parse import (
    app_name,
    field,
    cutoff_from_hours,
    decode_exception,
    describe_exception,
    format_time,
    parse_event,
    parse_time,
    payload_text,
    truncate,
)

MAX_EVENTS = 200
MAX_HOURS = 720.0
SCAN_CAP = 5000

CRASH_IDS = (1000, 1001, 1002, 1023, 1026)
SHUTDOWN_IDS = (12, 13, 41, 1001, 1074, 6005, 6006, 6008)

_CRASH_KINDS = {
    1000: "application_error",
    1002: "application_hang",
    1001: "wer",
    1023: "dotnet",
    1026: "dotnet",
}

_SHUTDOWN_KINDS = {
    41: "unexpected_restart",
    6008: "unexpected_shutdown",
    1074: "initiated_shutdown",
    6005: "event_log_started",
    6006: "event_log_stopped",
    12: "os_started",
    13: "os_shutdown",
}

# Bugcheck codes that show up in Kernel-Power 41 / WER-SystemErrorReporting 1001.
BUGCHECK_CODES = {
    0x0000000A: "IRQL_NOT_LESS_OR_EQUAL",
    0x0000001A: "MEMORY_MANAGEMENT",
    0x0000001E: "KMODE_EXCEPTION_NOT_HANDLED",
    0x0000003B: "SYSTEM_SERVICE_EXCEPTION",
    0x00000050: "PAGE_FAULT_IN_NONPAGED_AREA",
    0x0000007E: "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED",
    0x0000009F: "DRIVER_POWER_STATE_FAILURE",
    0x000000BE: "ATTEMPTED_WRITE_TO_READONLY_MEMORY",
    0x000000D1: "DRIVER_IRQL_NOT_LESS_OR_EQUAL",
    0x000000EF: "CRITICAL_PROCESS_DIED",
    0x00000133: "DPC_WATCHDOG_VIOLATION",
    0x00000139: "KERNEL_SECURITY_CHECK_FAILURE",
    0x00000154: "UNEXPECTED_STORE_EXCEPTION",
    0x0000021A: "STATUS_SYSTEM_PROCESS_TERMINATED",
}

_CHANNEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/\-]{0,255}$")
_PROVIDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/\-]{0,255}$")


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _number(args: Dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    raw = args.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(default)
    return max(low, min(high, value))


def _integers(args: Dict[str, Any], key: str, default: Sequence[int] = ()) -> List[int]:
    raw = args.get(key)
    if raw is None:
        return list(default)
    if isinstance(raw, (int, float, str)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return list(default)
    values: List[int] = []
    for item in raw:
        try:
            number = int(str(item).strip(), 10)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= 65535:
            values.append(number)
    return values


def _event_id_xpath(ids: Iterable[int]) -> str:
    clauses = " or ".join(f"EventID={int(i)}" for i in ids)
    return f"*[System[({clauses})]]" if clauses else "*"


def _collect(
    channel: str,
    xpath: str,
    cutoff,
    limit: int,
    scan_cap: int = SCAN_CAP,
) -> Tuple[List[Dict[str, Any]], int, bool]:
    """Query newest-first until *cutoff* is crossed, returning parsed records."""
    records: List[Dict[str, Any]] = []
    scanned = 0
    truncated = False
    for xml in evtlog.iter_events(channel, xpath, scan_cap):
        scanned += 1
        try:
            record = parse_event(xml)
        except Exception:
            continue
        moment = parse_time(record.get("time"))
        if moment is None:
            continue
        if moment < cutoff:
            truncated = False
            break
        records.append(record)
        if len(records) >= limit:
            break
        if scanned >= scan_cap:
            truncated = True
            break
    return records, scanned, truncated


def _matches_process(record: Dict[str, Any], needle: str) -> bool:
    needle = needle.lower()
    candidates = [app_name(record) or ""]
    data = record.get("data") or {}
    for key in ("Application Path", "AppPath", "Faulting Module Name"):
        value = field(data, key)
        if value:
            candidates.append(str(value))
    if any(needle in candidate.lower() for candidate in candidates):
        return True
    return needle in payload_text(record).lower()


def _crash_record(record: Dict[str, Any]) -> Dict[str, Any]:
    data = record.get("data") or {}
    event_id = int(record.get("event_id") or 0)
    provider = (record.get("provider") or "").lower()
    kind = _CRASH_KINDS.get(event_id, "other")
    # The same event id is reused by unrelated providers: 1000/1001 are common
    # "informational" ids for app-specific providers, so classify by provider too.
    if event_id == 1000 and "application error" not in provider:
        kind = "other"
    if event_id == 1002 and "application hang" not in provider:
        kind = "other"
    if event_id == 1001 and "error reporting" not in provider:
        kind = "other"
    if event_id in (1023, 1026) and ".net runtime" not in provider:
        kind = "other"
    if kind == "other":
        return {"kind": "other"}
    if event_id in (1023, 1026):
        text = payload_text(record)
        item: Dict[str, Any] = {
            "kind": "dotnet",
            "time": format_time(parse_time(record.get("time"))),
            "app": app_name(record),
            "event_id": event_id,
            "provider": record.get("provider"),
            "level": record.get("level"),
            "exception_text": truncate(text, 600),
        }
        return item

    exception = describe_exception(field(data, "Exception Code", "ExceptionCode"))
    item = {
        "kind": kind,
        "time": format_time(parse_time(record.get("time"))),
        "app": app_name(record),
        "app_version": field(data, "Application Version", "P2"),
        "app_path": field(data, "Application Path", "AppPath"),
        "module": field(data, "Faulting Module Name", "ModName"),
        "module_path": field(data, "Faulting Module Path", "Module Path"),
        "exception": exception,
        "offset": field(data, "Fault Offset"),
        "event_name": field(data, "EventName"),
        "bucket": field(data, "Bucket"),
        "report_id": field(data, "Report Id", "ReportId"),
        "process_id": record.get("process_id"),
        "event_id": event_id,
        "provider": record.get("provider"),
        "level": record.get("level"),
    }
    return {key: value for key, value in item.items() if value not in (None, "")}


def _group(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for event in events:
        app = (event.get("app") or "unknown").lower()
        signature = (
            event.get("exception")
            or event.get("event_name")
            or event.get("kind")
            or "unknown"
        )
        key = (app, str(signature))
        entry = buckets.setdefault(
            key,
            {
                "app": event.get("app") or "unknown",
                "signature": signature,
                "count": 0,
                "first": event.get("time"),
                "last": event.get("time"),
                "modules": [],
            },
        )
        entry["count"] += 1
        if event.get("time") and (entry["first"] is None or event["time"] < entry["first"]):
            entry["first"] = event["time"]
        if event.get("time") and (entry["last"] is None or event["time"] > entry["last"]):
            entry["last"] = event["time"]
        module = event.get("module")
        if module and module not in entry["modules"]:
            entry["modules"].append(module)
    groups = sorted(buckets.values(), key=lambda item: item["count"], reverse=True)
    for group in groups:
        group["modules"] = group["modules"][:5]
    return groups


def _bugcheck_name(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    candidates: List[int] = []
    if text.lower().startswith("0x"):
        try:
            candidates.append(int(text, 16))
        except ValueError:
            pass
    else:
        # Providers render the code as decimal or hex depending on the event source.
        for base in (16, 10):
            try:
                candidates.append(int(text, base))
            except ValueError:
                continue
    for value in candidates:
        if value and value in BUGCHECK_CODES:
            return BUGCHECK_CODES[value]
    return None


def win_crash_events(args: Dict[str, Any], **kwargs: Any) -> str:
    """Crash, hang, Windows Error Reporting and .NET-runtime events over a window."""
    try:
        hours = _number(args, "hours", 24, 0.1, MAX_HOURS)
        limit = int(_number(args, "limit", 25, 1, MAX_EVENTS))
        process = str(args.get("process") or "").strip()
        kinds = args.get("kinds")
        wanted = None
        if isinstance(kinds, (list, tuple)) and kinds:
            wanted = {str(kind).strip().lower() for kind in kinds}
        cutoff = cutoff_from_hours(hours)
        records, scanned, truncated = _collect(
            "Application", _event_id_xpath(CRASH_IDS), cutoff, SCAN_CAP
        )
        events: List[Dict[str, Any]] = []
        for record in records:
            event = _crash_record(record)
            if event.get("kind") == "other":
                continue
            if wanted is not None and event.get("kind") not in wanted:
                continue
            if process and not _matches_process(record, process):
                continue
            events.append(event)
            if len(events) >= limit:
                break
        events.sort(key=lambda item: item.get("time") or "", reverse=True)
        notes = [f"scanned {scanned} Application events in the last {hours:g}h"]
        if truncated:
            notes.append("stopped at the scan cap before reaching the window start")
        if not events:
            notes.append(
                "no crash records in this window; a process that was killed by an "
                "external tool (task manager, a supervisor, a job object) leaves no "
                "Application log entry -- check win_eventlog_query on System for "
                "service-control events instead"
            )
        return _ok(
            window_hours=hours,
            matched=len(events),
            scanned=scanned,
            events=events,
            groups=_group(events),
            notes=notes,
        )
    except evtlog.EventLogError as exc:
        return _fail(str(exc), code=exc.code)
    except Exception as exc:  # pragma: no cover - defensive
        return _fail(f"crash query failed: {exc}")


def win_shutdown_events(args: Dict[str, Any], **kwargs: Any) -> str:
    """Unexpected restarts, bugchecks and shutdown/start markers from the System log."""
    try:
        hours = _number(args, "hours", 168, 0.1, MAX_HOURS)
        limit = int(_number(args, "limit", 30, 1, MAX_EVENTS))
        cutoff = cutoff_from_hours(hours)
        records, scanned, truncated = _collect(
            "System", _event_id_xpath(SHUTDOWN_IDS), cutoff, SCAN_CAP
        )
        events: List[Dict[str, Any]] = []
        for record in records:
            data = record.get("data") or {}
            event_id = int(record.get("event_id") or 0)
            provider = record.get("provider") or ""
            kind = _SHUTDOWN_KINDS.get(event_id, "other")
            if event_id == 1001:
                if "systemerrorreporting" not in provider.lower() and "bugcheck" not in provider.lower():
                    continue
                kind = "bugcheck"
            item = {
                "kind": kind,
                "time": format_time(parse_time(record.get("time"))),
                "event_id": event_id,
                "provider": provider,
                "level": record.get("level"),
            }
            if event_id == 41:
                code = field(data, "BugcheckCode")
                item["bugcheck_code"] = code
                item["bugcheck"] = _bugcheck_name(code)
                item["power_button"] = field(data, "PowerButtonTimestamp")
                item["sleep_in_progress"] = field(data, "SleepInProgress")
            if kind == "bugcheck":
                code = field(data, "BugcheckCode")
                item["bugcheck_code"] = code
                item["bugcheck"] = _bugcheck_name(code)
                item["parameters"] = [
                    field(data, f"BugcheckParameter{i}") for i in range(1, 5)
                ]
            if event_id == 1074:
                item["process"] = field(data, "param1", "Process")
                item["reason"] = field(data, "param2", "ReasonCode")
                item["comment"] = truncate(field(data, "param5", "Comment") or "", 200)
            events.append({key: value for key, value in item.items() if value not in (None, "")})
            if len(events) >= limit:
                break
        events.sort(key=lambda item: item.get("time") or "", reverse=True)
        notes = [f"scanned {scanned} System events in the last {hours:g}h"]
        if truncated:
            notes.append("stopped at the scan cap before reaching the window start")
        return _ok(
            window_hours=hours,
            matched=len(events),
            scanned=scanned,
            events=events,
            notes=notes,
        )
    except evtlog.EventLogError as exc:
        return _fail(str(exc), code=exc.code)
    except Exception as exc:  # pragma: no cover - defensive
        return _fail(f"shutdown query failed: {exc}")


def win_eventlog_query(args: Dict[str, Any], **kwargs: Any) -> str:
    """General structured query over any Event Log channel."""
    try:
        channel = str(args.get("channel") or "Application").strip()
        if not _CHANNEL_RE.match(channel):
            return _fail(
                "channel must be a plain log name such as Application, System or "
                "Microsoft-Windows-TaskScheduler/Operational"
            )
        hours = _number(args, "hours", 24, 0.1, MAX_HOURS)
        limit = int(_number(args, "limit", 20, 1, MAX_EVENTS))
        ids = _integers(args, "event_ids")
        levels = [level for level in _integers(args, "levels") if 1 <= level <= 5]
        provider = str(args.get("provider") or "").strip()
        if provider and not _PROVIDER_RE.match(provider):
            return _fail("provider must be an exact provider name without quotes")
        contains = str(args.get("contains") or "").strip().lower()
        include_details = bool(args.get("include_details", False))

        clauses: List[str] = []
        if ids:
            clauses.append("(" + " or ".join(f"EventID={event}" for event in ids) + ")")
        if levels:
            clauses.append("(" + " or ".join(f"Level={level}" for level in levels) + ")")
        if provider:
            clauses.append(f"Provider[@Name='{provider}']")
        xpath = f"*[System[{' and '.join(clauses)}]]" if clauses else "*"

        cutoff = cutoff_from_hours(hours)
        records, scanned, truncated = _collect(channel, xpath, cutoff, SCAN_CAP)
        events: List[Dict[str, Any]] = []
        for record in records:
            if provider and (record.get("provider") or "") != provider:
                continue
            if ids and int(record.get("event_id") or 0) not in ids:
                continue
            if levels and int(record.get("level_number") or 0) not in levels:
                continue
            if contains:
                haystack = " ".join(
                    [
                        record.get("provider") or "",
                        record.get("channel") or "",
                        payload_text(record),
                    ]
                ).lower()
                if contains not in haystack:
                    continue
            item = {
                "time": format_time(parse_time(record.get("time"))),
                "event_id": record.get("event_id"),
                "level": record.get("level"),
                "provider": record.get("provider"),
                "channel": record.get("channel"),
                "process_id": record.get("process_id"),
                "message": truncate(payload_text(record), 500),
            }
            if include_details:
                details = {
                    key: truncate(value, 300)
                    for key, value in list((record.get("data") or {}).items())[:20]
                }
                item["data"] = details
            events.append(item)
            if len(events) >= limit:
                break
        events.sort(key=lambda item: item.get("time") or "", reverse=True)
        notes = [f"scanned {scanned} events from {channel} in the last {hours:g}h"]
        if truncated:
            notes.append("stopped at the scan cap before reaching the window start")
        return _ok(
            channel=channel,
            window_hours=hours,
            matched=len(events),
            scanned=scanned,
            events=events,
            notes=notes,
        )
    except evtlog.EventLogError as exc:
        return _fail(str(exc), code=exc.code)
    except Exception as exc:  # pragma: no cover - defensive
        return _fail(f"event log query failed: {exc}")
