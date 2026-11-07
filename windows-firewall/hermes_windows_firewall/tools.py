"""Firewall tools: what the three profiles allow, and what each rule does."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import fwreg

MAX_ROWS = 400
NAME_CHARS = 90

DIRECTIONS = {"in", "out"}
PROFILE_WORDS = {"domain", "private", "public", "any"}

# what a value the registry did not write falls back to -- documented Windows
# behavior, reported as the default it is, never as a measured fact
BUILTIN_DEFAULTS = {
    "enabled": True,
    "default_inbound": "Block",
    "default_outbound": "Allow",
    "notifications_disabled": False,
}


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _truthy(raw: Any) -> bool:
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


def _ports(text: Any) -> Any:
    """A port spec travels as written: '2869', '1024-65535', lists, '*'."""
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    if value in ("*", "Any", "any"):
        return "any"
    return value


def _protocol_of(rule: Dict[str, Any]) -> Dict[str, Any]:
    raw = rule["fields"].get("protocol")
    if raw is None:
        return {"protocol": None}
    number = str(raw).strip()
    name = fwreg.PROTOCOL_NAMES.get(number)
    facts: Dict[str, Any] = {"protocol": name or number}
    try:
        facts["protocol_number"] = int(number)
    except ValueError:
        pass  # a non-numeric token stays as the protocol string alone
    return facts


def _active_of(rule: Dict[str, Any]) -> bool:
    raw = str(rule["fields"].get("active", "TRUE")).strip().upper()
    return raw == "TRUE"


def _profiles_of(rule: Dict[str, Any]) -> List[str]:
    raw = rule["fields"].get("profile")
    if raw is None:
        return ["any"]
    words = [part.strip().lower() for part in str(raw).split(",") if part.strip()]
    if not words or "any" in words:
        return ["any"]
    return words


def _program_of(rule: Dict[str, Any]) -> Dict[str, Any] | None:
    raw = rule["fields"].get("app")
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() == "any":
        return {"path": "any program", "ref": None}
    expanded = os.path.expandvars(text)
    program: Dict[str, Any] = {"path": expanded, "ref": None}
    if expanded != text:
        program["ref"] = text  # e.g. %SystemRoot%\system32\svchost.exe as written
    return program


def _scope_words(text: Any) -> Any:
    """An address scope in plain words; unknown tokens pass through verbatim."""
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    if value in ("*", "Any", "any"):
        return "any address"
    if value == "LocalSubnet":
        return "the local subnet"
    return value


def _addresses(rule: Dict[str, Any], prefix: str) -> List[Dict[str, Any]] | None:
    entries: List[Dict[str, Any]] = []
    for version in ("4", "6"):
        raw = rule["fields"].get(prefix + version)
        if raw is None:
            continue
        entries.append({"ip": f"IPv{version}", "scope": _scope_words(raw)})
    return entries or None


def _row(rule: Dict[str, Any]) -> Dict[str, Any]:
    program = _program_of(rule)
    row: Dict[str, Any] = {
        "id": rule["id"],
        "name": _clip(rule.get("name"), NAME_CHARS),
        "active": _active_of(rule),
        "action": rule["fields"].get("action"),
        "direction": rule["fields"].get("dir"),
        "profiles": _profiles_of(rule),
        **_protocol_of(rule),
        "local_ports": _ports(rule["fields"].get("lport")),
        "remote_ports": _ports(rule["fields"].get("rport")),
        "program": program["path"] if program else None,
        "service": rule["fields"].get("svc"),
        "source": rule["source"],
    }
    if rule.get("name_is_localized"):
        row["name_is_localized"] = True
    return row


def _profile_row(facts: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {"name": facts["name"], "display": facts["display"]}
    for key in ("enabled", "default_inbound", "default_outbound", "notifications_disabled"):
        row[key] = facts.get(key)
    if facts.get("extra"):
        row["extra"] = facts["extra"]
    return row


def _gather() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return fwreg.firewall_rules(), fwreg.profile_facts()


def win_firewall_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """The rule store and the three profile switches, each rule in plain words."""
    args = args or {}
    direction = str(args.get("direction") or "").strip().lower()
    profile_filter = str(args.get("profile") or "").strip().lower()
    active_wanted = args.get("active")
    active_filter = None if active_wanted is None or str(active_wanted).strip() == "" \
        else _truthy(active_wanted)
    query = str(args.get("query") or "").strip().lower()
    limit = _limit(args)

    try:
        rules, profiles = _gather()
    except fwreg.RegistryUnavailable as exc:
        return _fail(str(exc), code="registry_unavailable")

    def _matches(rule: Dict[str, Any]) -> bool:
        row_direction = str(rule["fields"].get("dir") or "").strip().lower()
        if direction and (direction not in DIRECTIONS or row_direction != direction):
            return False
        if profile_filter:
            if profile_filter not in PROFILE_WORDS:
                return False
            if profile_filter not in _profiles_of(rule):
                return False
        if active_filter is not None and _active_of(rule) != active_filter:
            return False
        if query:
            program = str(rule["fields"].get("app") or "").lower()
            service = str(rule["fields"].get("svc") or "").lower()
            name = str(rule.get("name") or "").lower()
            if not (query in name or query in rule["id"].lower()
                    or query in program or query in service):
                return False
        return True

    candidates = [rule for rule in rules if _matches(rule)]
    listed = sorted(candidates, key=lambda r: str(r.get("name") or r["id"]).lower())[:limit]

    inactive_total = sum(1 for r in rules if not _active_of(r))
    localized_total = sum(1 for r in rules if r.get("name_is_localized"))
    user_rules = sum(1 for r in rules if r["source"] == "user")

    notes: List[str] = [
        f"{len(listed)} of {len(candidates)} matching rule(s) listed, {len(rules)} in the store"
    ]
    firewalled_off = [p for p in profiles if p.get("enabled") is False]
    if firewalled_off:
        names = ", ".join(p["display"] for p in firewalled_off)
        notes.append(f"the firewall is SWITCHED OFF for: {names}")
    if inactive_total and active_filter is not False:
        notes.append(f"{inactive_total} rule(s) are switched off (active=false lists only them)")
    if localized_total:
        notes.append(
            f"{localized_total} built-in name(s) resolved from resource strings, "
            "shown in the machine's own language"
        )
    if not user_rules:
        notes.append("no per-user rule store exists on this build; all rules are the machine's")
    if len(candidates) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if not listed:
        notes.append("nothing matched; drop the query or the filters")
    if direction and direction not in DIRECTIONS:
        notes.append("direction is one of: in, out")
    if profile_filter and profile_filter not in PROFILE_WORDS:
        notes.append("profile is one of: domain, private, public, any")
    if any(value is None for p in profiles for value in (
            p.get("enabled"), p.get("default_inbound"), p.get("default_outbound"))):
        notes.append(
            "a null profile value means the registry did not write it; Windows then applies "
            "its builtin default (firewall on, inbound blocked, outbound allowed)"
        )

    return _ok(
        profiles=[_profile_row(p) for p in profiles],
        rules=[_row(r) for r in listed],
        notes=notes,
    )


def _sentence(rule: Dict[str, Any]) -> str:
    """What one rule does, as a sentence a person can read aloud."""
    fields = rule["fields"]
    verb = {"Allow": "allows", "Block": "blocks"}.get(str(fields.get("action")), "handles")
    side = {"In": "inbound", "Out": "outbound"}.get(str(fields.get("dir")), "traffic")
    protocol = _protocol_of(rule)["protocol"] or "traffic"
    pieces: List[str] = [f"{verb} {side} {protocol}"]
    local = _ports(fields.get("lport"))
    remote = _ports(fields.get("rport"))
    if local:
        pieces.append(f"to local port {local}")
    if remote:
        pieces.append(f"to remote port {remote}")
    remote_scope = _addresses(rule, "ra")
    if remote_scope:
        scope = " and ".join(entry["scope"] for entry in remote_scope)
        pieces.append(f"from {scope}")
    program = _program_of(rule)
    service = fields.get("svc")
    if service:
        host = f"svchost.exe hosting service {service}" if program else f"service {service}"
        pieces.append(f"for {host}")
    elif program:
        pieces.append(f"for {program['path']}")
    profiles = _profiles_of(rule)
    where = "every profile" if profiles == ["any"] else f"the {' and '.join(profiles)} profile"
    pieces.append(f"in {where}")
    sentence = ", ".join(pieces)
    if not _active_of(rule):
        sentence += " -- but the rule is SWITCHED OFF and matches nothing"
    return sentence


def win_firewall_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One rule in full: every field, the modelled ones read and the rest verbatim."""
    args = args or {}
    requested = str(args.get("name") or "").strip()
    if not requested:
        return _fail("give the rule's id or a part of its name, e.g. 'NETDIS-SSDPSrv-Out-UDP-Active'", code="name_required")

    try:
        rules, _profiles = _gather()
    except fwreg.RegistryUnavailable as exc:
        return _fail(str(exc), code="registry_unavailable")

    low = requested.lower()
    exact = [r for r in rules if r["id"].lower() == low]
    if not exact:
        exact = [r for r in rules if low in r["id"].lower()]
    if not exact:
        exact = [r for r in rules if low in str(r.get("name") or "").lower()]
    if not exact:
        suggestions = sorted({r["id"] for r in rules
                              if low[:4] and low[:4] in r["id"].lower()})[:5]
        return _fail(
            f"no firewall rule named {requested} is in the store",
            code="rule_not_found",
            suggestions=suggestions,
            hint="win_firewall_table lists every rule with its id and name",
        )

    rule = exact[0]
    fields = rule["fields"]
    name_ref = fields.get("name")
    desc_ref = fields.get("desc")
    group_ref = fields.get("embedctxt")
    notes: List[str] = []
    if not _active_of(rule):
        notes.append("the rule is switched off (Active=FALSE): it matches nothing until it is enabled")
    if fields.get("svc") and fields.get("app"):
        notes.append("the program is the svchost host; the service is the actual actor -- "
                     "scope by the service when writing rules")
    edge = fields.get("edge")
    if edge and str(edge).strip().upper() not in ("FALSE",):
        notes.append(f"edge traversal is on ({edge}): the rule's traffic may ride through "
                     "NAT edge paths such as Teredo")
    if not fields.get("app") and not fields.get("svc"):
        notes.append("the rule is not scoped to any program or service: it applies to whatever "
                     "matches its ports and addresses")

    return _ok(
        id=rule["id"],
        name=rule.get("name"),
        name_reference=name_ref,
        name_is_localized=rule.get("name_is_localized", False) or None,
        active=_active_of(rule),
        sentence=_sentence(rule),
        action=fields.get("action"),
        direction=fields.get("dir"),
        profiles=_profiles_of(rule),
        **_protocol_of(rule),
        local_ports=_ports(fields.get("lport")),
        remote_ports=_ports(fields.get("rport")),
        local_addresses=_addresses(rule, "la"),
        remote_addresses=_addresses(rule, "ra"),
        program=_program_of(rule),
        service=fields.get("svc"),
        edge=edge,
        group=rule.get("group"),
        group_reference=group_ref,
        description=rule.get("desc"),
        description_reference=desc_ref,
        store_version=rule["version"],
        source=rule["source"],
        other_fields=rule.get("extra") or None,
        notes=notes,
    )


__all__ = ["win_firewall_detail", "win_firewall_table"]
