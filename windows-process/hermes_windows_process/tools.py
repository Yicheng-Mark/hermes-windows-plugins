"""Process-table tool: what is running on this machine, what started it, and what outlived it."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from . import proctab

MAX_ROWS = 500
_PATH_LIMIT = 220
_WINDIR = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"

PARENT_ALIVE = "alive"
PARENT_GONE = "gone"
PARENT_REUSED = "reused"
PARENT_UNKNOWN = "unknown"
PARENT_ROOT = "root"


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _int_list(raw: Any) -> List[int]:
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    values: List[int] = []
    for item in items:
        try:
            value = int(str(item).strip(), 10)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            values.append(value)
    return values


def _wanted_pids(args: Dict[str, Any]) -> Set[int]:
    wanted: Set[int] = set()
    if args.get("pid") is not None:
        wanted.update(_int_list(args.get("pid")))
    if args.get("pids") is not None:
        wanted.update(_int_list(args.get("pids")))
    return wanted


def _limit(args: Dict[str, Any]) -> int:
    try:
        value = int(float(args.get("limit", 100)))
    except (TypeError, ValueError):
        value = 100
    return max(1, min(MAX_ROWS, value))


def _short_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if len(path) <= _PATH_LIMIT else path[:_PATH_LIMIT] + "..."


def classify_parent(
    child_started: Optional[float],
    parent_pid: int,
    parent_started: Optional[float],
    parent_present: bool,
) -> str:
    """Say whether a process's recorded parent is the one that actually spawned it.

    Windows stores the parent PID, not a handle: once the parent exits, its PID is free for
    reuse, and a child that keeps running then points at an unrelated newer process. A parent
    that started *after* the child cannot have spawned it, so that case is a reused PID, not
    a live parent.
    """
    if parent_pid == 0:
        return PARENT_ROOT
    if not parent_present:
        return PARENT_GONE
    if child_started and parent_started:
        return PARENT_REUSED if parent_started > child_started else PARENT_ALIVE
    return PARENT_UNKNOWN


def _iso(epoch: Optional[float]) -> Optional[str]:
    if not epoch:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _aged(epoch: Optional[float], now: float) -> Optional[int]:
    if not epoch:
        return None
    return max(0, int(now - epoch))


def _build_table() -> Tuple[Dict[int, Dict[str, Any]], int]:
    """Enrich the snapshot rows with path and start time (missing when not ours to read)."""
    rows = proctab.snapshot()
    opened = 0
    table: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        path, started = proctab.details(row["pid"])
        if path is not None or started is not None:
            opened += 1
        entry = dict(row)
        entry["path"] = path
        entry["started"] = started
        table[row["pid"]] = entry
    return table, len(rows) - opened


def _is_system(path: Optional[str]) -> bool:
    """True for a Windows-tree image, or for any process this account cannot open.

    Session and bootstrap processes (csrss, wininit, winlogon, services, explorer) live under
    the Windows directory and are started by a parent that exits by design, so they hold a
    dead parent PID forever without being a leak.
    """
    if not path:
        return True
    return path.lower().startswith(_WINDIR.lower().rstrip("\\") + "\\")


def _entry(row: Dict[str, Any], table: Dict[int, Dict[str, Any]], now: float) -> Dict[str, Any]:
    parent_pid = row["parent_pid"]
    parent = table.get(parent_pid)
    state = classify_parent(
        row.get("started"),
        parent_pid,
        parent.get("started") if parent else None,
        parent is not None,
    )
    return {
        "pid": row["pid"],
        "parent_pid": parent_pid,
        "process": row["name"],
        "path": _short_path(row.get("path")),
        "started": _iso(row.get("started")),
        "age_seconds": _aged(row.get("started"), now),
        "threads": row["threads"],
        "parent_process": parent["name"] if parent else None,
        "parent_state": state,
        "system": _is_system(row.get("path")),
    }


def win_process_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """List processes with their parent, start time and whether that parent is still the real one."""
    try:
        wanted = _wanted_pids(args)
        process_filter = str(args.get("process") or "").strip().lower()
        parent_filter = args.get("parent")
        parent_pid = _int_list(parent_filter)[0] if parent_filter is not None else None
        orphans_only = bool(args.get("orphans_only", False))
        with_ancestry = bool(args.get("with_ancestry", False))
        include_system = bool(args.get("include_system", True))
        limit = _limit(args)

        table, unreadable = _build_table()
        now = time.time()
        rows = {pid: _entry(row, table, now) for pid, row in table.items()}

        candidates: List[Dict[str, Any]] = []
        for pid, entry in rows.items():
            if not include_system and entry["system"]:
                continue
            if wanted and pid not in wanted:
                continue
            if parent_pid is not None and entry["parent_pid"] != parent_pid:
                continue
            if process_filter:
                haystack = f"{entry['process']} {entry['path'] or ''}".lower()
                if process_filter not in haystack:
                    continue
            if orphans_only and entry["parent_state"] not in (PARENT_GONE, PARENT_REUSED):
                continue
            candidates.append(entry)

        candidates.sort(key=lambda item: (not item["age_seconds"], -(item["age_seconds"] or 0), item["pid"]))
        entries = candidates[:limit]

        context_rows: List[Dict[str, Any]] = []
        if with_ancestry and entries:
            seen: Set[int] = {entry["pid"] for entry in entries}
            for entry in list(entries):
                pid = entry["parent_pid"]
                while pid and pid not in seen:
                    seen.add(pid)
                    ancestor = table.get(pid)
                    if ancestor is None:
                        break
                    ancestor_entry = _entry(ancestor, table, now)
                    ancestor_entry["context"] = True
                    context_rows.append(ancestor_entry)
                    pid = ancestor["parent_pid"]

        gone = sum(1 for entry in rows.values() if entry["parent_state"] == PARENT_GONE)
        reused = sum(1 for entry in rows.values() if entry["parent_state"] == PARENT_REUSED)
        system_orphans = sum(
            1
            for entry in rows.values()
            if entry["system"] and entry["parent_state"] in (PARENT_GONE, PARENT_REUSED)
        )

        notes = [f"{len(entries)} of {len(table)} process(es) matched"]
        if gone or reused:
            notes.append(
                f"{gone + reused} process(es) have a parent that is gone ({gone}) or whose "
                f"PID was reused ({reused})"
            )
        if system_orphans:
            notes.append(
                f"{system_orphans} of them are Windows session/bootstrap processes "
                "(csrss, wininit, winlogon, services, explorer) whose parent exits by design; "
                "set include_system=false to leave them out"
            )
        if unreadable:
            notes.append(
                f"{unreadable} process(es) could not be opened (System, Idle or another "
                "account): no path or start time, parent state may read 'unknown'"
            )
        if len(candidates) > len(entries):
            notes.append(f"stopped at limit={limit}; raise it or narrow the filter")
        if not entries:
            notes.append(
                "nothing matched; drop the filters to see the whole table, or set "
                "orphans_only=false"
            )

        return _ok(
            matched=len(entries),
            total_processes=len(table),
            orphans=gone + reused,
            orphans_gone=gone,
            orphans_reused=reused,
            entries=entries,
            ancestry=context_rows,
            notes=notes,
        )
    except proctab.WinProcError as exc:
        return _fail(str(exc), code=exc.code)
    except Exception as exc:  # pragma: no cover - defensive
        return _fail(f"process lookup failed: {exc}")
