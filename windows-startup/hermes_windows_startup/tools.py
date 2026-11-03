"""Startup tools: what launches itself, from where, and what the person switched off."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import startupdirs, startupreg

MAX_ROWS = 400
COMMAND_CHARS = 200

SCOPES = {"user", "machine"}


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


def _clip(text: Any, chars: int) -> Any:
    if not isinstance(text, str):
        return text
    text = text.strip()
    return text if len(text) <= chars else text[:chars] + "…"


def _gather() -> tuple[List[Dict[str, Any]], Dict[tuple[str, str], Dict[str, Any]]]:
    """Every autostart entry (registry + folders) and Explorer's approval records."""
    entries = startupreg.run_entries() + startupdirs.folders(startupreg.shell_folder)
    approvals = startupreg.approvals()
    for entry in entries:
        record = approvals.get((entry["source"], entry["name"]))
        if record is None and entry["source"].startswith("folder-"):
            # folder approvals are keyed by the file's full name; some Windows
            # versions record the stem -- try both before declaring no record
            stem = os.path.splitext(str(entry["name"]))[0]
            record = approvals.get((entry["source"], stem))
        entry["approved"] = record
    return entries, approvals


def _enabled_state(entry: Dict[str, Any]) -> str:
    record = entry.get("approved")
    if record is None:
        return "enabled"  # no record means Explorer never wrote a verdict: it runs
    return str(record.get("state"))


def _row(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": entry.get("name"),
        "command": _clip(entry.get("command"), COMMAND_CHARS),
        "source": entry.get("source"),
        "scope": entry.get("scope"),
        "enabled": _enabled_state(entry),
        "changed": (entry.get("approved") or {}).get("changed"),
    }


def _binary_state(command: str | None, isfile=None) -> Dict[str, Any] | None:
    """Whether the launched binary is still on disk, arguments and quoting included.

    Unquoted commands with spaces in the path (real machines write them: this one
    carries ``C:\\...\\CC Switch\\cc-switch.exe`` bare) are resolved the way the
    loader resolves them: the longest whitespace prefix that names a real file
    wins; when none does, the first token is reported as the missing binary.
    """
    if not command:
        return None
    check = isfile or os.path.isfile
    text = str(command).strip()
    if not text:
        return None
    if text.startswith('"'):
        path = text.split('"', 2)[1] if '"' in text[1:] else text.strip('"')
        candidates = [path]
    else:
        parts = text.split()
        candidates = [" ".join(parts[:count]) for count in range(len(parts), 0, -1)]
    for candidate in candidates:
        resolved = os.path.expandvars(os.path.expanduser(candidate))
        if not os.path.isabs(resolved):
            return {"path": resolved, "present": None, "note": "the path is not absolute; not checked"}
        if check(resolved):
            return {"path": resolved, "present": True, "note": None}
    missing = os.path.expandvars(os.path.expanduser(candidates[-1]))
    return {
        "path": missing,
        "present": False,
        "note": "the launched binary is not on disk any more",
    }


def win_startup_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """Everything that launches itself at sign-in, and what was switched off."""
    args = args or {}
    query = str(args.get("query") or "").strip().lower()
    scope_filter = str(args.get("scope") or "").strip().lower()
    include_disabled = _truthy(args.get("include_disabled"), True)
    limit = _limit(args)

    try:
        entries, approvals = _gather()
    except startupreg.RegistryUnavailable as exc:
        return _fail(str(exc), code="registry_unavailable")

    rows = [_row(entry) for entry in entries]
    known = {(entry["source"], entry["name"]) for entry in entries}
    orphans = [
        {"name": name, "source": source, **facts}
        for (source, name), facts in approvals.items()
        if (source, name) not in known
    ]

    candidates = [
        row
        for row in rows
        if (not query or query in str(row.get("name") or "").lower() or query in str(row.get("command") or "").lower())
        and (not scope_filter or str(row.get("scope") or "").lower() == scope_filter)
        and (include_disabled or row.get("enabled") != "disabled")
    ]

    listed = candidates[:limit]
    disabled = sum(1 for row in rows if row.get("enabled") == "disabled")
    machine = sum(1 for row in rows if row.get("scope") == "machine")

    notes = [f"{len(listed)} of {len(candidates)} matching entr(y/ies) listed, {len(rows)} autostart entries total, {machine} machine-scoped"]
    if len(candidates) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if disabled:
        notes.append(f"{disabled} switched off in Task Manager; include_disabled=false hides them")
    if orphans:
        notes.append(f"{len(orphans)} approval record(s) remain for entries that are gone (uninstalled programs leave them behind)")
    if not listed:
        notes.append("nothing matched; drop the query or the filters")
    if scope_filter and scope_filter not in SCOPES:
        notes.append(f"scope is one of: {', '.join(sorted(SCOPES))}")

    payload: Dict[str, Any] = {"startup": listed, "notes": notes}
    if orphans:
        payload["leftover_approvals"] = orphans[:20]
    return _ok(**payload)


def win_startup_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One autostart entry in full: what it launches, whether that still exists, and its verdict."""
    args = args or {}
    requested = str(args.get("name") or "").strip()
    if not requested:
        return _fail("give the entry's name, e.g. OneDrive or SecurityHealth", code="name_required")

    try:
        entries, _ = _gather()
    except startupreg.RegistryUnavailable as exc:
        return _fail(str(exc), code="registry_unavailable")

    low = requested.lower()
    exact = [entry for entry in entries if str(entry.get("name")).lower() == low]
    if not exact:
        near = [
            str(entry.get("name"))
            for entry in entries
            if low in str(entry.get("name") or "").lower() or low in str(entry.get("command") or "").lower()
        ]
        if not near:
            return _fail(
                f"no autostart entry named {requested} is registered",
                code="not_registered",
                suggestions=[],
                hint="win_startup_table lists every entry with its exact name",
            )
        exact = [entry for entry in entries if str(entry.get("name")).lower() == str(near[0]).lower()]

    entry = exact[0]
    row = _row(entry)
    binary = _binary_state(entry.get("command"))
    file_facts = entry.get("file")

    notes: List[str] = []
    if binary and binary.get("present") is False:
        notes.append(str(binary["note"]))
    if row.get("enabled") == "disabled":
        notes.append("switched off in Task Manager (StartupApproved): it does not run, but it is still registered")
    if str(row.get("enabled", "")).startswith("unknown"):
        notes.append("Explorer's verdict byte is not one of the documented states; reported as-is")

    return _ok(
        name=row["name"],
        command=entry.get("command"),
        source=row["source"],
        scope=row["scope"],
        enabled=row["enabled"],
        changed=row["changed"],
        binary=binary,
        file=file_facts,
        notes=notes,
    )


__all__ = ["win_startup_detail", "win_startup_table"]
