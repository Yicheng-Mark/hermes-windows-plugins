"""Scheduled-task tools: what this machine runs on its own, when, and as whom."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from . import taskpowershell, taskxml

MAX_ROWS = 500
ACTION_CHARS = 240

# what the Scheduler writes into LastTaskResult, in the words a person needs
RESULT_MEANINGS = {
    0x00000000: "success",
    0x00041300: "ready to run",
    0x00041301: "running now",
    0x00041302: "disabled",
    0x00041303: "has not run yet",
    0x00041304: "no more runs are scheduled",
    0x00041305: "a required property is not set",
    0x00041306: "terminated by the user",
    0x80070002: "the program or script could not be found",
    0x80070003: "the path could not be found",
    0x80070005: "access was denied",
    0x8007000E: "not enough memory",
    0x80070020: "the file is in use by another process",
    0x8007010B: "the working directory does not exist",
    0x80040154: "the COM class it runs is not registered",
    0x40010004: "it was terminated (stopped or timed out)",
    0x8004131F: "the task is already running",
    0x80041321: "the task's definition is corrupt or was tampered with",
    0x800710E0: "it needs an interactive desktop and ran without one",
}

# the cmdlet's trigger classes, in the words a listing can carry
TRIGGER_NAMES = {
    "MSFT_TaskBootTrigger": "at startup",
    "MSFT_TaskLogonTrigger": "at logon",
    "MSFT_TaskTimeTrigger": "at a time",
    "MSFT_TaskDailyTrigger": "daily",
    "MSFT_TaskWeeklyTrigger": "weekly",
    "MSFT_TaskMonthlyTrigger": "monthly",
    "MSFT_TaskMonthlyDOWTrigger": "monthly by weekday",
    "MSFT_TaskEventTrigger": "on event",
    "MSFT_TaskIdleTrigger": "when idle",
    "MSFT_TaskRegistrationTrigger": "at registration",
    "MSFT_TaskSessionStateChangeTrigger": "on session change",
}

# "no result at all" rather than a failure: a task nobody has run yet
NOT_A_FAILURE = {0x00000000, 0x00041300, 0x00041301, 0x00041303}


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


def normalise(path: str) -> str:
    """A task path with one leading backslash and no trailing one: ``\\A\\B``."""
    text = str(path).strip().replace("/", "\\")
    if not text:
        return ""
    return "\\" + text.lstrip("\\").rstrip("\\")


def _inside_microsoft(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith("\\microsoft\\") or lowered == "\\microsoft"


def _clip(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    text = " ".join(text.split())
    return text if len(text) <= ACTION_CHARS else text[:ACTION_CHARS] + "…"


def result_of(code: Any) -> Dict[str, Any] | None:
    """A ``last_result`` as a number, its hex and what it means."""
    if code is None:
        return None
    try:
        value = int(code)
    except (TypeError, ValueError):
        return {"code": code, "meaning": None}
    unsigned = value & 0xFFFFFFFF  # the Scheduler writes it unsigned; JSON may carry it signed
    return {
        "code": unsigned,
        "hex": f"0x{unsigned:08X}",
        "meaning": RESULT_MEANINGS.get(unsigned, "no known meaning"),
    }


def _failed(row: Dict[str, Any]) -> bool:
    result = row.get("last_result") or {}
    code = result.get("code")
    return isinstance(code, int) and code not in NOT_A_FAILURE


def _row(raw: Dict[str, Any]) -> Dict[str, Any]:
    triggers = [TRIGGER_NAMES.get(str(name), str(name)) for name in (raw.get("triggers") or [])]
    return {
        "path": raw.get("path"),
        "state": raw.get("state"),
        "run_as": raw.get("user") or raw.get("group"),
        "run_level": raw.get("run_level"),
        "action": _clip(raw.get("action")),
        "action_count": raw.get("action_count"),
        "triggers": triggers,
        "last_run": raw.get("last_run"),
        "last_result": result_of(raw.get("last_result")),
        "next_run": raw.get("next_run"),
        "missed_runs": raw.get("missed_runs"),
    }


def win_scheduled_tasks(args: Dict[str, Any], **kwargs: Any) -> str:
    """Every scheduled task on this Windows machine, with its state and when it runs next."""
    args = args or {}
    query = str(args.get("query") or "").strip().lower()
    include_microsoft = _truthy(args.get("include_microsoft"), False)
    failed_only = _truthy(args.get("failed_only"), False)
    state_filter = str(args.get("state") or "").strip().lower()
    limit = _limit(args)

    try:
        raw = taskpowershell.tasks()
    except taskpowershell.PowerShellError as exc:
        return _fail(str(exc), code="tasks_unavailable")

    rows = [_row(item) for item in raw]
    candidates = [
        row
        for row in rows
        if (include_microsoft or not _inside_microsoft(str(row.get("path") or "")))
        and (not query or query in str(row.get("path") or "").lower())
        and (not state_filter or str(row.get("state") or "").lower() == state_filter)
        and (not failed_only or _failed(row))
    ]

    listed = candidates[:limit]
    failures = [row["path"] for row in rows if _failed(row)]
    notes = [f"{len(listed)} of {len(candidates)} matching task(s) listed, {len(rows)} registered"]
    if len(candidates) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if failures:
        notes.append(
            f"{len(failures)} task(s) last ended with a failure; failed_only=true shows them"
        )
    if not include_microsoft:
        notes.append("Windows' own tasks are left out; set include_microsoft=true to see them")
    if not listed:
        notes.append("nothing matched; drop the query or the state filter")
    if state_filter and state_filter not in {"ready", "running", "disabled", "queued", "unknown"}:
        notes.append("state is one of ready, running, disabled, queued, unknown")

    return _ok(
        matched=len(listed),
        candidates=len(candidates),
        registered_total=len(rows),
        failing_total=len(failures),
        entries=listed,
        notes=notes,
    )


def win_scheduled_task_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One scheduled task in full: its triggers with their boundaries, its actions and settings."""
    args = args or {}
    requested = normalise(args.get("name") or args.get("path") or "")
    if not requested:
        return _fail("give the task's path, e.g. \\\\Hermes_Gateway", code="name_required")

    try:
        raw = taskpowershell.tasks()
    except taskpowershell.PowerShellError as exc:
        return _fail(str(exc), code="tasks_unavailable")
    rows = [_row(item) for item in raw]
    by_path = {str(row.get("path") or "").lower(): row for row in rows}
    row = by_path.get(requested.lower())
    if row is None:
        near = [
            str(item.get("path"))
            for item in rows
            if requested.strip("\\").lower() in str(item.get("path") or "").lower()
        ]
        return _fail(
            f"no scheduled task is registered at {requested}",
            code="not_registered",
            suggestions=near[:5],
            hint="win_scheduled_tasks lists every registered path",
        )

    notes: List[str] = []
    parsed: Dict[str, Any] | None = None
    try:
        exported = taskpowershell.definition(requested)
    except taskpowershell.PowerShellError as exc:
        exported = {"error": str(exc)}
    xml = exported.get("xml")
    if xml:
        try:
            parsed = taskxml.parse_definition(taskxml.strip_declaration(xml).encode("utf-8"))
        except taskxml.TaskXmlError as exc:
            notes.append(f"the definition could not be read: {exc}")
    else:
        notes.append(
            "the definition could not be exported (the task may run as another account): "
            f"{exported.get('error') or 'no reason given'}"
        )

    triggers = []
    for trigger in (parsed or {}).get("triggers") or []:
        triggers.append({**trigger, "description": taskxml.describe_trigger(trigger)})
    actions = []
    for action in (parsed or {}).get("actions") or []:
        actions.append({**action, "description": taskxml.describe_action(action)})

    settings = (parsed or {}).get("settings") or {}
    if parsed and not triggers and settings.get("maintenance"):
        notes.append(
            "no triggers: this task runs during automatic maintenance, which is why it has "
            "MaintenanceSettings instead"
        )

    return _ok(
        path=row["path"],
        state=row["state"],
        run_as=row["run_as"],
        run_level=row["run_level"],
        last_run=row["last_run"],
        last_result=row["last_result"],
        next_run=row["next_run"],
        missed_runs=row["missed_runs"],
        action=row["action"],
        registration=(parsed or {}).get("registration"),
        principal=(parsed or {}).get("principal"),
        settings=(parsed or {}).get("settings"),
        triggers=triggers,
        actions=actions,
        notes=notes,
    )


__all__ = ["result_of", "win_scheduled_task_detail", "win_scheduled_tasks"]
