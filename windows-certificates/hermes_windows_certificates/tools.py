"""Certificate tools: what is in the stores, and one certificate in full."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import certstore, oids

MAX_ROWS = 400
SUBJECT_CHARS = 200
EXPIRING_DAYS = 30
SECONDS_PER_DAY = 86400

_STATE_RANK = {"expired": 0, "not_yet_valid": 1, "expiring": 2, "valid": 3}


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


def _limit(args: Dict[str, Any]) -> int:
    try:
        value = int(float(args.get("limit", 100)))
    except (TypeError, ValueError):
        value = 100
    return max(1, min(value, MAX_ROWS))


def _clip(text: Any, chars: int) -> Any:
    if not isinstance(text, str):
        return text
    text = " ".join(text.split())
    return text if len(text) <= chars else text[:chars] + "…"


def _iso_local(epoch: Optional[float]) -> Optional[str]:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def validity(now: float, not_before: Optional[float], not_after: Optional[float]) -> Dict[str, Any]:
    """The window in words: state, days left, and a sentence a person can read."""
    if not_before is None or not_after is None:
        return {"state": "unknown", "days_left": None, "note": "no validity window on this certificate"}
    if now < not_before:
        days = int((not_before - now) // SECONDS_PER_DAY)
        return {
            "state": "not_yet_valid",
            "days_left": None,
            "note": f"not valid until {_iso_local(not_before)} ({days} day(s) away)",
        }
    if now > not_after:
        days_ago = int((now - not_after) // SECONDS_PER_DAY)
        note = "expired less than a day ago" if days_ago == 0 else f"expired {days_ago} day(s) ago"
        return {"state": "expired", "days_left": -days_ago, "note": note}
    days_left = int((not_after - now) // SECONDS_PER_DAY)
    if days_left <= EXPIRING_DAYS:
        return {"state": "expiring", "days_left": days_left,
                "note": f"expires in {days_left} day(s)" if days_left > 0 else "expires today"}
    return {"state": "valid", "days_left": days_left,
            "note": f"valid for {days_left} more day(s)"}


def _scopes(args: Dict[str, Any]) -> tuple[list[str], Optional[str]]:
    context = str(args.get("context") or "both").strip().lower()
    contexts = {"user": ["user"], "machine": ["machine"]}.get(context, ["user", "machine"])
    store = str(args.get("store") or "").strip()
    store = store.upper() if store else None
    return contexts, store


def _row_of(facts: Dict[str, Any], now: float) -> Dict[str, Any]:
    window = validity(now, facts.get("not_before"), facts.get("not_after"))
    return {
        "context": facts.get("context"),
        "store": facts.get("store"),
        "subject": _clip(facts.get("subject"), SUBJECT_CHARS),
        "issuer": _clip(facts.get("issuer"), SUBJECT_CHARS),
        "self_signed": facts.get("self_signed"),
        "valid_from": _iso_local(facts.get("not_before")),
        "until": _iso_local(facts.get("not_after")),
        "days_left": window["days_left"],
        "state": window["state"],
        "note": window["note"],
        "thumbprint": facts.get("thumbprint"),
    }


def win_cert_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """Every certificate in the stores walked, the troubled ones on top."""
    args = args or {}
    limit = _limit(args)
    expired_only = _truthy(args.get("expired_only"), False)
    query = str(args.get("query") or "").strip().lower()
    contexts, store = _scopes(args)

    if not certstore.available():
        return _fail("the Windows certificate stores are only readable on Windows",
                     code="windows_only")
    stores = [store] if store else list(certstore.DEFAULT_STORES)
    try:
        facts = certstore.iter_certs(contexts=contexts, stores=stores)
    except certstore.CertstoreError as exc:
        return _fail(str(exc), code="stores_unavailable")

    now = time.time()
    rows = [_row_of(item, now) for item in facts]

    matching = []
    for row in rows:
        if expired_only and row["state"] not in ("expired", "expiring", "not_yet_valid"):
            continue
        if query and query not in " ".join(
            str(row.get(key) or "") for key in ("subject", "issuer")
        ).lower():
            continue
        matching.append(row)

    matching.sort(key=lambda row: (_STATE_RANK.get(str(row["state"]), 9),
                                   row["days_left"] if row["days_left"] is not None else 10**9))
    listed = matching[:limit]

    notes = [f"{len(listed)} of {len(matching)} matching certificate(s) listed, "
             f"{len(rows)} walked in {len(contexts)} context(s) x {len(stores)} store(s)"]
    if len(matching) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it (max 400) or narrow the query")
    troubled = sum(1 for row in rows if row["state"] in ("expired", "expiring", "not_yet_valid"))
    if troubled and not expired_only:
        notes.append(f"{troubled} of {len(rows)} expired, expiring within {EXPIRING_DAYS} days, "
                     f"or not valid yet; expired_only=true lists them")
    roots = sum(1 for row in rows if row["self_signed"])
    if roots:
        notes.append(f"{roots} self-signed (root certificates carry their own name twice)")
    notes.append("sorted with the expired first, then by days left")
    if not listed:
        notes.append("nothing matched; drop the query or the filters")

    return _ok(certificates=listed, notes=notes)


def _detail_of(facts: Dict[str, Any], now: float) -> Dict[str, Any]:
    window = validity(now, facts.get("not_before"), facts.get("not_after"))
    key = facts.get("public_key") or {}
    algorithm_oid = key.get("algorithm_oid")
    curve = oids.curve_of(key.get("parameters") or b"")
    purposes = facts.get("eku_oids")
    purpose_rows = None
    if purposes is not None:
        purpose_rows = [{"oid": oid, "name": oids.purpose_name(oid)} for oid in purposes]
    return {
        "context": facts.get("context"),
        "store": facts.get("store"),
        "subject": facts.get("subject"),
        "issuer": facts.get("issuer"),
        "friendly_name": facts.get("friendly_name"),
        "serial": facts.get("serial_hex"),
        "version": f"v{facts.get('version')}",
        "thumbprint": facts.get("thumbprint"),
        "signature_algorithm": {
            "oid": facts.get("signature_oid"),
            "name": oids.signature_name(facts.get("signature_oid")),
        },
        "public_key": {
            "algorithm": {
                "oid": algorithm_oid,
                "name": oids.public_key_name(algorithm_oid),
            },
            "bits": oids.key_bits(algorithm_oid, key.get("key_bytes") or b"",
                                  key.get("parameters") or b""),
            "curve": curve,
        },
        "purposes": purpose_rows,
        "purposes_note": (None if purposes is not None
                          else "no EKU extension: this certificate does not restrict its purposes"),
        "self_signed": facts.get("self_signed"),
        "validity": {
            "not_before": _iso_local(facts.get("not_before")),
            "not_after": _iso_local(facts.get("not_after")),
            "state": window["state"],
            "note": window["note"],
        },
    }


def _normalize_thumbprint(raw: Any) -> str:
    return "".join(ch for ch in str(raw or "") if ch in "0123456789abcdefABCDEF").upper()


def win_cert_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One certificate in full, by thumbprint or by name."""
    args = args or {}
    thumbprint = _normalize_thumbprint(args.get("thumbprint"))
    query = str(args.get("query") or "").strip().lower()
    contexts, store = _scopes(args)

    if not certstore.available():
        return _fail("the Windows certificate stores are only readable on Windows",
                     code="windows_only")
    if not thumbprint and not query:
        return _fail("give a thumbprint or a query; the tools cannot read minds", code="usage")
    stores = [store] if store else list(certstore.DEFAULT_STORES)
    try:
        facts = certstore.iter_certs(contexts=contexts, stores=stores)
    except certstore.CertstoreError as exc:
        return _fail(str(exc), code="stores_unavailable")

    now = time.time()
    if thumbprint:
        matching = [item for item in facts
                    if _normalize_thumbprint(item.get("thumbprint")) == thumbprint]
    else:
        matching = []
        for item in facts:
            haystack = " ".join(str(item.get(key) or "")
                                for key in ("subject", "issuer", "friendly_name"))
            if query in haystack.lower():
                matching.append(item)

    if not matching:
        return _fail("no certificate matched", code="no_match",
                     hint="win_cert_table lists thumbprints")

    if len(matching) > 1 and thumbprint:
        # one thumbprint, several copies: user and machine can both hold it
        notes = [f"{len(matching)} copies of this certificate exist"]
    elif len(matching) > 1:
        candidates = [
            {"subject": _clip(item.get("subject"), 80),
             "thumbprint": item.get("thumbprint"),
             "context": item.get("context"),
             "store": item.get("store")}
            for item in matching[:25]
        ]
        notes = [f"{len(matching)} certificates matched; the first 25 below - "
                 f"pick one by thumbprint"]
        return _ok(candidates=candidates, notes=notes)
    else:
        notes = []

    return _ok(certificate=_detail_of(matching[0], now), notes=notes,
               others=[{"context": m.get("context"), "store": m.get("store")}
                       for m in matching[1:6]] if len(matching) > 1 else None)


__all__ = ["validity", "win_cert_detail", "win_cert_table"]
