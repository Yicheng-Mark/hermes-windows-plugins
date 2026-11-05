"""Update tools: what Windows installed lately, and when it was last patched."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from . import resultcodes, wuquery

MAX_COUNT = 500
MAX_ROWS = 400
TITLE_CHARS = 200


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


def _clip(text: Any, chars: int) -> Any:
    if not isinstance(text, str):
        return text
    text = " ".join(text.split())
    return text if len(text) <= chars else text[:chars] + "…"


def _count(args: Dict[str, Any]) -> int:
    try:
        value = int(float(args.get("count", 50)))
    except (TypeError, ValueError):
        value = 50
    return max(1, min(value, MAX_COUNT))


def _limit(args: Dict[str, Any]) -> int:
    try:
        value = int(float(args.get("limit", 100)))
    except (TypeError, ValueError):
        value = 100
    return max(1, min(value, MAX_ROWS))


def _entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    categories = raw.get("categories")
    if isinstance(categories, str):
        categories = [categories]  # a single category is not wrapped in a list
    return {
        "date": raw.get("date"),
        "title": _clip(raw.get("title"), TITLE_CHARS),
        "result": resultcodes.result_of(raw.get("result_code")),
        "hresult": resultcodes.hresult_of(raw.get("hresult")),
        "support_url": raw.get("support_url") or None,
        "categories": categories if isinstance(categories, list) else [],
    }


def win_update_history(args: Dict[str, Any], **kwargs: Any) -> str:
    """The newest updates this machine installed or attempted, and how each ended."""
    args = args or {}
    count = _count(args)
    only_failures = _truthy(args.get("only_failures"), False)
    query = str(args.get("query") or "").strip().lower()

    try:
        raw = wuquery.history(count)
    except wuquery.PowerShellError as exc:
        return _fail(str(exc), code="history_unavailable")

    entries = [_entry(item) for item in raw["entries"]]
    known = int(raw.get("total") or 0)

    matching = [
        entry
        for entry in entries
        if (not only_failures or resultcodes.is_failed(entry.get("result")))
        and (not query or query in str(entry.get("title") or "").lower())
    ]
    listed = matching[:count]

    notes = [f"{len(listed)} of {len(matching)} matching update(s) listed, {known} in the history"]
    if len(matching) > len(listed):
        notes.append(f"stopped at count={count}; raise it (max 500)")
    if known > len(entries):
        notes.append(f"the history reaches back further than the newest {len(entries)}; count goes up to 500")
    failed = sum(1 for entry in entries if resultcodes.is_failed(entry.get("result")))
    if failed and not only_failures:
        notes.append(f"{failed} of the newest {len(entries)} did not end clean; only_failures=true lists them")
    if not listed:
        notes.append(
            "nothing matched"
            + ("; every update in this window ended clean" if only_failures else "; drop the query or the filter")
        )

    return _ok(updates=listed, notes=notes)


def win_hotfix_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """The OS-level hotfixes, newest install date first."""
    args = args or {}
    query = str(args.get("query") or "").strip().lower()
    limit = _limit(args)

    try:
        raw = wuquery.hotfixes()
    except wuquery.PowerShellError as exc:
        return _fail(str(exc), code="hotfixes_unavailable")

    # newest install date first, the entries without a date after them: the 'is not None'
    # flag is the first key so a reversed sort keeps the dated rows on top
    rows = sorted(
        raw,
        key=lambda item: (item.get("installed_on") is not None,
                          "" if item.get("installed_on") is None else str(item["installed_on"]),
                          str(item.get("id") or "")),
        reverse=True,
    )

    matching = [row for row in rows if not query or query in str(row.get("id") or "").lower()]
    listed = matching[:limit]

    notes = [f"{len(listed)} of {len(matching)} hotfix(es) listed, {len(rows)} known"]
    if len(matching) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if not listed:
        notes.append("nothing matched; drop the query")
    notes.append("the quick-fix list carries OS-level updates only; win_update_history answers what Windows installed in full")

    return _ok(hotfixes=listed, notes=notes)


__all__ = ["win_hotfix_table", "win_update_history"]
