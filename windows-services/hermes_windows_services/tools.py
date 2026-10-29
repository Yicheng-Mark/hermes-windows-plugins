"""Service tools: what runs as a service, why one failed, and what depends on what."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import exitcodes, svcquery, svcreg

MAX_ROWS = 400
BINARY_CHARS = 160
DESCRIPTION_CHARS = 240

START_MODES = {"boot", "system", "auto", "manual", "disabled"}
STATES = {"running", "stopped", "paused", "start pending", "stop pending", "continue pending", "pause pending", "unknown"}


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
    text = " ".join(text.split())
    return text if len(text) <= chars else text[:chars] + "…"


def start_of(raw: Dict[str, Any]) -> str:
    """The start mode, with the delayed flag folded in the way Services shows it."""
    start = str(raw.get("start") or "unknown").strip()
    if raw.get("delayed"):
        start += ", delayed"
    return start


def _row(raw: Dict[str, Any], depends: List[str], dependents: List[str]) -> Dict[str, Any]:
    pid = int(raw.get("pid") or 0)
    return {
        "name": raw.get("name"),
        "display": raw.get("display"),
        "state": raw.get("state"),
        "start": start_of(raw),
        "pid": pid or None,
        "exit_code": exitcodes.exit_of(raw.get("exit_code")),
        "account": raw.get("account"),
        "binary": _clip(raw.get("binary"), BINARY_CHARS),
        "depends_on": depends,
        "dependents": dependents,
    }


def _registry_facts(names: List[str]) -> Dict[str, Dict[str, Any]]:
    """Dependencies and delayed flags for every service, in one registry sweep."""
    facts: Dict[str, Dict[str, Any]] = {}
    for name in names:
        try:
            facts[str(name)] = {
                "depends_on": svcreg.depends_on(str(name)),
                "delayed": svcreg.delayed_start(str(name)),
            }
        except svcreg.RegistryUnavailable:
            break  # one flat "no registry" answer is enough; CIM's delayed flag still carries
    return facts


def _reverse(facts: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """Who waits for whom, answered the other way around."""
    dependents: Dict[str, List[str]] = {}
    for name, item in facts.items():
        for target in item.get("depends_on") or []:
            key = str(target).replace(" (group)", "").strip().lower()
            dependents.setdefault(key, []).append(name)
    return dependents


def _failed(row: Dict[str, Any]) -> bool:
    code = (row.get("exit_code") or {}).get("code")
    return isinstance(code, int) and code not in exitcodes.NOT_A_FAILURE


def _binary_state(binary: str | None) -> Dict[str, Any] | None:
    """Whether the registered binary is still on disk, svchost arguments and all."""
    if not binary:
        return None
    text = str(binary).strip()
    if text.startswith('"'):
        path = text.split('"', 2)[1] if '"' in text[1:] else text.strip('"')
    else:
        path = text.split()[0] if text.split() else text
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isabs(path):
        return {"path": path, "present": None, "note": "the path is not absolute; not checked"}
    present = os.path.isfile(path)
    return {
        "path": path,
        "present": present,
        "note": None if present else "the registered binary is not on disk any more",
    }


def win_service_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """Every service on this Windows machine, with its state and what it waits for."""
    args = args or {}
    query = str(args.get("query") or "").strip().lower()
    state_filter = str(args.get("state") or "").strip().lower()
    start_filter = str(args.get("start") or "").strip().lower()
    nonzero_exit = _truthy(args.get("nonzero_exit"), False)
    limit = _limit(args)

    try:
        raw = svcquery.services()
    except svcquery.PowerShellError as exc:
        return _fail(str(exc), code="services_unavailable")

    facts = _registry_facts([item.get("name") for item in raw])
    dependents = _reverse(facts)

    rows = [
        _row(
            {**item, "delayed": bool(item.get("delayed")) or facts.get(str(item.get("name")), {}).get("delayed", False)},
            facts.get(str(item.get("name")), {}).get("depends_on") or [],
            dependents.get(str(item.get("name") or "").lower()) or [],
        )
        for item in raw
    ]

    candidates = [
        row
        for row in rows
        if (not query or query in str(row.get("name") or "").lower() or query in str(row.get("display") or "").lower())
        and (not state_filter or str(row.get("state") or "").lower() == state_filter)
        and (not start_filter or str(row.get("start") or "").lower().startswith(start_filter))
        and (not nonzero_exit or _failed(row))
    ]

    listed = candidates[:limit]
    failing = [str(row["name"]) for row in rows if _failed(row)]
    running = sum(1 for row in rows if str(row.get("state") or "").lower() == "running")

    notes = [f"{len(listed)} of {len(candidates)} matching service(s) listed, {len(rows)} registered, {running} running"]
    if len(candidates) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if failing:
        notes.append(f"{len(failing)} service(s) carry a non-zero exit code; nonzero_exit=true shows them")
    if not listed:
        notes.append("nothing matched; drop the query or the filters")
    if state_filter and state_filter not in STATES:
        notes.append(f"state is one of: {', '.join(sorted(STATES))}")
    if start_filter and start_filter not in START_MODES:
        notes.append(f"start is one of: {', '.join(sorted(START_MODES))} (a ', delayed' suffix matches start=auto)")

    return _ok(services=listed, notes=notes)


def win_service_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One service in full: what Windows does when it fails, and the events behind its exit code."""
    args = args or {}
    requested = str(args.get("name") or "").strip()
    if not requested:
        return _fail("give the service's name, e.g. wuauserv", code="name_required")

    try:
        raw = svcquery.services()
    except svcquery.PowerShellError as exc:
        return _fail(str(exc), code="services_unavailable")

    by_name = {str(item.get("name") or "").lower(): item for item in raw}
    item = by_name.get(requested.lower())
    if item is None:
        near = [
            str(other.get("name"))
            for other in raw
            if requested.lower() in str(other.get("name") or "").lower()
            or requested.lower() in str(other.get("display") or "").lower()
        ]
        return _fail(
            f"no service named {requested} is registered",
            code="not_registered",
            suggestions=near[:5],
            hint="win_service_table lists every registered service",
        )

    name = str(item.get("name"))
    facts = _registry_facts([name]).get(name.lower(), {}) or {}
    dependents = _reverse({name: facts}).get(name.lower()) or []
    row = _row({**item, "delayed": bool(item.get("delayed")) or facts.get("delayed", False)},
               facts.get("depends_on") or [], dependents)

    notes: List[str] = []
    registry_ok = True
    try:
        policy = svcreg.failure_policy(name)
    except svcreg.RegistryUnavailable:
        policy = None
        registry_ok = False
        notes.append("the registry could not be read; the failure policy is not shown")
    if registry_ok and not (policy and policy.get("actions")):
        notes.append("no failure action is configured: Windows leaves this service dead when it fails")

    binary = _binary_state(item.get("binary"))
    if binary and binary.get("present") is False:
        notes.append(str(binary["note"]))

    try:
        events = svcquery.failures(name)
    except svcquery.PowerShellError:
        events = []
        notes.append("the System event log could not be read; recent failures are not shown")

    return _ok(
        name=row["name"],
        display=row["display"],
        state=row["state"],
        start=row["start"],
        pid=row["pid"],
        exit_code=row["exit_code"],
        account=row["account"],
        binary=binary,
        description=_clip(item.get("description"), DESCRIPTION_CHARS),
        depends_on=row["depends_on"],
        dependents=row["dependents"],
        failure_policy=policy,
        recent_failures=[
            {"time": event.get("time"),
             "what_happened": exitcodes.sc_event_of(event.get("id")),
             "event_id": event.get("id"),
             "message": _clip(event.get("what"), DESCRIPTION_CHARS)}
            for event in events
        ],
        notes=notes,
    )


__all__ = ["win_service_detail", "win_service_table"]
