"""Installed-software tools: what is installed, which version, and how it would leave."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from . import appreg

MAX_ROWS = 400
PUBLISHER_CHARS = 60
COMMAND_CHARS = 300

VIEWS = {"machine-64", "machine-32", "user-64", "user-32"}


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


def _dwordish(raw: Any) -> bool:
    """A publisher flag that means 'on' when written as 1, '1' or 0x1."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw != 0
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "0x1", "true", "yes"}
    return False


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


def _size_mb(raw: Any) -> float | None:
    """EstimatedSize is a DWORD in kilobytes; surfaced as megabytes, one decimal."""
    try:
        return round(float(raw) / 1024, 1)
    except (TypeError, ValueError):
        return None


def _install_date(raw: Any) -> str | None:
    """InstallDate is written as YYYYMMDD or a localized date; both are read."""
    if raw is None:
        return None
    text = str(raw).strip()
    if len(text) == 8 and text.isdigit():
        try:
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        except ValueError:
            return text
    for pattern in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return text


def _classify_uninstaller(command: Any, msi_managed: bool) -> Dict[str, Any] | None:
    """What kind of remover the publisher registered -- described, never run."""
    if command is None or not str(command).strip():
        if msi_managed:
            return {"kind": "windows installer", "note": "no explicit string; the MSI database owns removal"}
        return None
    text = str(command).strip()
    low = text.lower()
    if "msiexec" in low:
        return {"kind": "msiexec", "note": "an MSI product code; removal goes through Windows Installer"}
    if "removeappxpackage" in low or "appx" in low:
        return {"kind": "appx", "note": "a Store-side package; Settings removes it, not this string"}
    # the remover is the first quoted segment (paths carry spaces) or the first
    # bare token; arguments never classify it
    if text.startswith('"') and '"' in text[1:]:
        first = text.split('"', 2)[1].lower()
    else:
        tokens = text.split()
        first = tokens[0].lower() if tokens else ""
    if first.endswith(".exe"):
        return {"kind": "setup executable", "note": "the publisher's own uninstaller program"}
    if first.endswith((".cmd", ".bat", ".ps1")):
        return {"kind": "script", "note": "a script the publisher left behind"}
    if ".exe" in low:
        # an unquoted path with spaces in it (publishers write these): the
        # first token stops at the space, but the string names an executable
        return {"kind": "setup executable", "note": "the publisher's own uninstaller program"}
    return {"kind": "other", "note": "an undocumented command; read it before trusting it"}


def _gather() -> List[Dict[str, Any]]:
    return appreg.app_entries()


def _name_of(entry: Dict[str, Any]) -> str:
    return str(entry.get("displayname") or "").strip()


def _is_hidden(entry: Dict[str, Any]) -> bool:
    return _dwordish(entry.get("systemcomponent"))


def _collapse(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per program; a second view joins the first as a view list.

    The same DisplayName in two views is the 32/64-bit dual install Apps &
    Features itself shows once -- collapsing mirrors that, and keeps the
    machine-64 copy first because the sweep reads it first.
    """
    by_name: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for entry in entries:
        if entry.get("unreadable"):
            continue
        name = _name_of(entry)
        if not name:
            continue
        key = name.lower()
        if key not in by_name:
            row = dict(entry)
            row["views"] = [entry["view"]]
            by_name[key] = row
            order.append(key)
        else:
            views = by_name[key]["views"]
            if entry["view"] not in views:
                views.append(entry["view"])
                if not by_name[key].get("uninstallstring") and entry.get("uninstallstring"):
                    by_name[key]["uninstallstring"] = entry["uninstallstring"]
    return [by_name[key] for key in order]


def _row(entry: Dict[str, Any]) -> Dict[str, Any]:
    name = _name_of(entry)
    duplicated = len(entry["views"]) > 1
    row: Dict[str, Any] = {
        "name": name,
        "version": entry.get("displayversion"),
        "publisher": _clip(entry.get("publisher"), PUBLISHER_CHARS),
        "view": entry["view"],
        "size_mb": _size_mb(entry.get("estimatedsize")),
        "installed": _install_date(entry.get("installdate")),
        "hidden": _is_hidden(entry),
    }
    if duplicated:
        row["views"] = entry["views"]
    return row


def win_app_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """The software inventory behind Apps & Features, from the four Uninstall keys."""
    args = args or {}
    query = str(args.get("query") or "").strip().lower()
    view_filter = str(args.get("view") or "").strip().lower()
    include_hidden = _truthy(args.get("include_system_components"), False)
    limit = _limit(args)

    try:
        entries = _gather()
    except appreg.RegistryUnavailable as exc:
        return _fail(str(exc), code="registry_unavailable")

    unreadable = [e for e in entries if e.get("unreadable")]
    programs = _collapse(entries)
    hidden_count = sum(1 for e in programs if _is_hidden(e))
    candidates = [
        entry
        for entry in programs
        if (include_hidden or not _is_hidden(entry))
        and (
            not view_filter
            or view_filter not in VIEWS  # unknown view: not a filter, the note says so
            or view_filter in entry["views"]
        )
        and (
            not query
            or query in _name_of(entry).lower()
            or query in str(entry.get("publisher") or "").lower()
        )
    ]

    listed = sorted(candidates, key=lambda e: _name_of(e).lower())[:limit]
    duplicated = sum(1 for e in programs if len(e["views"]) > 1)

    notes = [
        f"{len(listed)} of {len(candidates)} matching program(s) listed, "
        f"{len(programs)} named programs across {len(entries)} registry entries"
    ]
    for view in ("machine-64", "machine-32", "user-64", "user-32"):
        count = sum(1 for e in entries if not e.get("unreadable") and e["view"] == view)
        if count:
            notes.append(f"{view}: {count} entries")
    if hidden_count and not include_hidden:
        notes.append(f"{hidden_count} hidden from Apps & Features (SystemComponent; include_system_components=true shows them)")
    if duplicated:
        notes.append(f"{duplicated} program(s) installed in more than one view (32/64-bit dual installs)")
    if unreadable:
        notes.append(f"{len(unreadable)} subkey(s) could not be read and are listed under unreadable")
    if len(candidates) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if not listed:
        notes.append("nothing matched; drop the query or the filters")
    if view_filter and view_filter not in VIEWS:
        notes.append(f"view is one of: {', '.join(sorted(VIEWS))}")

    payload: Dict[str, Any] = {"apps": [_row(e) for e in listed], "notes": notes}
    if unreadable:
        payload["unreadable"] = [e["subkey"] for e in unreadable][:10]
    return _ok(**payload)


def _occurrence(entry: Dict[str, Any], isdir=None) -> Dict[str, Any]:
    """One registry occurrence of a program: where it lives and what it says."""
    check = isdir or os.path.isdir
    location = str(entry.get("installlocation") or "").strip()
    location_state = None
    if location:
        expanded = os.path.expandvars(location)
        location_state = {
            "path": expanded,
            "exists": check(expanded) if os.path.isabs(expanded) else None,
        }
    return {
        "view": entry["view"],
        "subkey": entry.get("subkey"),
        "version": entry.get("displayversion"),
        "size_mb": _size_mb(entry.get("estimatedsize")),
        "installed": _install_date(entry.get("installdate")),
        "install_location": location_state,
        "uninstaller": _classify_uninstaller(
            entry.get("uninstallstring"), _dwordish(entry.get("windowsinstaller"))
        ),
        "uninstall_string": _clip(entry.get("uninstallstring"), COMMAND_CHARS),
    }


def win_app_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One program in full: every field the publisher wrote, read and classified."""
    args = args or {}
    requested = str(args.get("name") or "").strip()
    if not requested:
        return _fail("give the program's name, e.g. 'Python 3.13' or 'OBS Studio'", code="name_required")

    try:
        entries = _gather()
    except appreg.RegistryUnavailable as exc:
        return _fail(str(exc), code="registry_unavailable")

    programs = _collapse(entries)
    low = requested.lower()
    exact = [p for p in programs if _name_of(p).lower() == low]
    if not exact:
        near = [p for p in programs if low in _name_of(p).lower()]
        if not near:
            suggestions = sorted({_name_of(p) for p in programs if low[:4] in _name_of(p).lower()})[:5]
            return _fail(
                f"no installed program named {requested} is registered",
                code="not_installed",
                suggestions=suggestions,
                hint="win_app_table lists every program with its exact name",
            )
        exact = [near[0]]

    entry = exact[0]
    occurrences = [_occurrence(e) for e in entries
                   if not e.get("unreadable") and _name_of(e).lower() == _name_of(entry).lower()]

    notes: List[str] = []
    missing_locations = [o["install_location"] for o in occurrences
                         if o["install_location"] and o["install_location"]["exists"] is False]
    if missing_locations:
        notes.append("the recorded install folder is not on disk any more -- an uninstalled program's leftovers, or a moved install")
    if any(o["uninstall_string"] is None and o["uninstaller"] is None for o in occurrences):
        notes.append("no uninstall command is registered; Apps & Features offers no Remove for it")
    if _dwordish(entry.get("nomodify")) and _dwordish(entry.get("norepair")):
        notes.append("the publisher locked modification and repair")
    if len(occurrences) > 1:
        views = ", ".join(o["view"] for o in occurrences)
        notes.append(f"registered in {len(occurrences)} views ({views}): the 32/64-bit dual-install shape")

    return _ok(
        name=_name_of(entry),
        publisher=entry.get("publisher"),
        icon=entry.get("displayicon"),
        help_link=entry.get("helplink"),
        about_link=entry.get("urlinfoabout"),
        comments=entry.get("comments"),
        msi_managed=_dwordish(entry.get("windowsinstaller")) or None,
        hidden=_is_hidden(entry),
        occurrences=occurrences,
        notes=notes,
    )


__all__ = ["win_app_detail", "win_app_table"]
