"""Port-owner tool: which process holds a local port on this machine."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import iphlp

MAX_ROWS = 500
_PATH_LIMIT = 220


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _ports(args: Dict[str, Any]) -> List[int]:
    raw: Any = args.get("port")
    extra = args.get("ports")
    items: List[Any] = []
    if raw is not None:
        items.extend(raw if isinstance(raw, (list, tuple)) else [raw])
    if extra is not None:
        items.extend(extra if isinstance(extra, (list, tuple)) else [extra])
    values: List[int] = []
    for item in items:
        try:
            value = int(str(item).strip(), 10)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 65535:
            values.append(value)
    return values


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


def win_port_owners(args: Dict[str, Any], **kwargs: Any) -> str:
    """List local TCP/UDP endpoints with the owning PID and image name."""
    try:
        ports = _ports(args)
        protocol = str(args.get("protocol") or "both").strip().lower()
        if protocol not in ("tcp", "udp", "both"):
            return _fail("protocol must be one of tcp, udp, both")
        wanted_state = str(args.get("state") or "all").strip().lower()
        include_ipv6 = bool(args.get("include_ipv6", True))
        process_filter = str(args.get("process") or "").strip().lower()
        limit = _limit(args)

        rows: List[Dict[str, Any]] = []
        if protocol in ("tcp", "both"):
            rows.extend(iphlp.tcp_rows(include_ipv6))
        if protocol in ("udp", "both"):
            rows.extend(iphlp.udp_rows(include_ipv6))

        entries: List[Dict[str, Any]] = []
        for row in rows:
            if ports and row["port"] not in ports:
                continue
            if wanted_state != "all":
                state = row.get("state") or ""
                if wanted_state in ("listen", "listening"):
                    if state != "listen":
                        continue
                elif state != wanted_state:
                    continue
            name = iphlp.process_name(row["pid"])
            base = name.rsplit("\\", 1)[-1] if name else None
            if process_filter:
                haystack = f"{base or ''} {name or ''}".lower()
                if process_filter not in haystack:
                    continue
            entries.append({
                "protocol": row["protocol"],
                "address": row["address"],
                "port": row["port"],
                "state": row["state"],
                "pid": row["pid"],
                "process": base,
                "path": _short_path(name),
                "remote_address": row.get("remote_address"),
                "remote_port": row.get("remote_port"),
            })
            if len(entries) >= limit:
                break

        by_process: Dict[str, int] = {}
        for entry in entries:
            key = entry.get("process") or f"pid {entry['pid']}"
            by_process[key] = by_process.get(key, 0) + 1
        listeners = sum(1 for entry in entries if entry["state"] == "listen")

        notes = [f"{len(entries)} endpoint(s) matched out of {len(rows)} in the table"]
        if entries and len(entries) >= limit:
            notes.append(f"stopped at limit={limit}; raise it or filter by port/process")
        if not entries:
            notes.append(
                "no endpoint matched; drop the state filter to see established "
                "connections, or check the port list"
            )
        return _ok(
            matched=len(entries),
            listeners=listeners,
            total_endpoints=len(rows),
            entries=entries,
            by_process=dict(sorted(by_process.items(), key=lambda item: item[1], reverse=True)[:10]),
            notes=notes,
        )
    except iphlp.WinNetError as exc:
        return _fail(str(exc), code=exc.code)
    except Exception as exc:  # pragma: no cover - defensive
        return _fail(f"port lookup failed: {exc}")
