"""Device tools: which device is unhappy, what it needs, and what drives it."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from . import codes, devquery

MAX_ROWS = 300
NAME_CHARS = 120


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _truthy(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _limit(args: Dict[str, Any], default: int = 100) -> int:
    try:
        value = int(float(args.get("limit", default)))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, MAX_ROWS))


def _clip(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    text = " ".join(text.split())
    return text if len(text) <= NAME_CHARS else text[:NAME_CHARS] + "…"


def _row(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": _clip(raw.get("name")) or "(unnamed)",
        "class": raw.get("class"),
        "status": raw.get("status"),
        "problem": codes.code_of(raw.get("code")),
        "manufacturer": _clip(raw.get("manufacturer")),
        "device_id": raw.get("device_id"),
    }


def _broken(row: Dict[str, Any]) -> bool:
    code = (row.get("problem") or {}).get("code")
    return codes.broken(code)


def win_device_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """Every PnP device on this Windows machine, with the unhappy ones called out."""
    args = args or {}
    query = str(args.get("query") or "").strip().lower()
    class_filter = str(args.get("class") or "").strip().lower()
    broken_only = _truthy(args.get("broken_only"), False)
    include_absent = _truthy(args.get("include_absent"), False)
    limit = _limit(args)

    try:
        raw = devquery.devices()
    except devquery.PowerShellError as exc:
        return _fail(str(exc), code="devices_unavailable")

    present = [item for item in raw if _truthy(item.get("present"), True)]
    rows = [_row(item) for item in (raw if include_absent else present)]

    candidates = [
        row
        for row in rows
        if (not query or query in str(row.get("name") or "").lower()
            or query in str(row.get("device_id") or "").lower())
        and (not class_filter or str(row.get("class") or "").lower() == class_filter)
        and (not broken_only or _broken(row))
    ]

    listed = candidates[:limit]
    unhappy = [row for row in rows if _broken(row)]
    by_class: Dict[str, int] = {}
    for row in rows:
        key = str(row.get("class") or "(no class)")
        by_class[key] = by_class.get(key, 0) + 1

    notes = [
        f"{len(listed)} of {len(candidates)} matching device(s) listed, "
        f"{len(present)} present, {len(rows) - len(present)} historical"
    ]
    if len(candidates) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if unhappy:
        names = ", ".join(f"{row['name']} ({(row['problem'] or {}).get('meaning')})" for row in unhappy[:5])
        notes.append(f"{len(unhappy)} device(s) need attention: {names}")
    if not listed:
        notes.append("nothing matched; drop the query or the class filter")
    top_classes = ", ".join(f"{k}: {v}" for k, v in sorted(by_class.items(), key=lambda kv: -kv[1])[:5])
    notes.append(f"largest classes: {top_classes}")

    return _ok(devices=listed, notes=notes)


def win_device_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One device in full: the driver behind it, or the absence of one."""
    args = args or {}
    requested = str(args.get("name") or str(args.get("device_id") or "")).strip()
    if not requested:
        return _fail("give the device's name or id, e.g. 'camera' or a DeviceID "
                     "from win_device_table", code="name_required")

    try:
        raw = devquery.devices()
    except devquery.PowerShellError as exc:
        return _fail(str(exc), code="devices_unavailable")

    lowered = requested.lower()
    present = [item for item in raw if _truthy(item.get("present"), True)]
    match = None
    for item in present:
        if str(item.get("device_id") or "").lower() == lowered:
            match = item
            break
    if match is None:
        for item in present:
            if lowered in str(item.get("name") or "").lower() or lowered in str(item.get("device_id") or "").lower():
                match = item
                break
    if match is None:
        near = [str(item.get("name")) for item in present
                if lowered.split()[0] in str(item.get("name") or "").lower()]
        return _fail(
            f"no present device matches {requested}",
            code="not_found",
            suggestions=_clip_list(near[:5]),
            hint="win_device_table lists every present device",
        )

    row = _row(match)
    notes: List[str] = []
    driver = None
    try:
        table = devquery.drivers()
    except devquery.PowerShellError:
        table = []
        notes.append("the driver table could not be read; the driver section is not shown")
    for entry in table:
        if str(entry.get("device_id") or "") == str(match.get("device_id") or ""):
            driver = {
                "name": _clip(entry.get("device_name")),
                "class": entry.get("class"),
                "version": entry.get("version"),
                "date": (entry.get("date") or "")[:10] or None,
                "provider": _clip(entry.get("provider")),
                "signer": _clip(entry.get("signer")),
                "inf": entry.get("inf"),
                "signed": bool(entry.get("signed")),
            }
            break

    problem = row.get("problem") or {}
    if problem.get("code") == 28:
        notes.append("no driver is installed: Windows has the device but nothing to run it — "
                     "the driver section being empty below is the same fact")
    elif problem.get("code") == 22:
        notes.append("this device is switched off on purpose; nothing is broken")
    if driver and not driver["signed"]:
        notes.append("the driver is not signed")

    return _ok(
        name=row["name"],
        class_name=row["class"],
        status=row["status"],
        problem=problem,
        manufacturer=row["manufacturer"],
        device_id=row["device_id"],
        driver=driver,
        notes=notes,
    )


def _clip_list(items: list) -> list:
    return [_clip(item) for item in items]


__all__ = ["win_device_detail", "win_device_table"]
