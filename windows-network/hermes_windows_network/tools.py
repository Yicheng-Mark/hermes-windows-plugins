"""Adapter tools: is this machine's network healthy, and which adapter is the problem."""

from __future__ import annotations

import ipaddress
import json
from typing import Any, Dict, List

from . import netpowershell

MAX_ROWS = 200
DESC_CHARS = 120

# what `Get-NetAdapter`'s Status can say, lowered; the names are enum values and do not
# change with the display language (checked on a machine set to Chinese)
KNOWN_STATES = {"up", "disconnected", "disabled", "not present", "testing"}

STATE_PROBLEMS = {
    "up": None,
    "disconnected": "no medium: no cable is plugged in, or the wireless network is not joined",
    "disabled": "switched off on purpose; nothing is broken",
    "not present": "its hardware is not present (the ghost of a radio or slot that is gone)",
    "testing": None,
}

# description fragments that name a virtual adapter even when the adapter's own flag
# is missing; every one of these is a product name, not a translated word. A Bluetooth
# adapter is deliberately absent: its network interface is software but its radio is
# real hardware, so it is not a virtual adapter.
VIRTUAL_PATTERNS = (
    "hyper-v",
    "virtual",
    "virtualbox",
    "vmware",
    "tap-windows",
    "wintun",
    "wireguard",
    "loopback",
    "wan miniport",
    "wi-fi direct",
    "kernel debug",
    "microsoft hosted network",
)


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


def _limit(args: Dict[str, Any], default: int = 50) -> int:
    try:
        value = int(float(args.get("limit", default)))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, MAX_ROWS))


def _clip(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    text = " ".join(text.split())
    return text if len(text) <= DESC_CHARS else text[:DESC_CHARS] + "…"


def _state(raw: Any) -> str:
    """The adapter's state, lowered; an unknown word is carried through, never guessed."""
    text = str(raw or "").strip().lower()
    return text or "unknown"


def _speed(bps: Any) -> str | None:
    """A number of bits per second in a person's words; no speed is None, not zero."""
    if not isinstance(bps, (int, float)) or isinstance(bps, bool) or bps <= 0:
        return None
    for unit, factor in (("Gbps", 1_000_000_000), ("Mbps", 1_000_000), ("kbps", 1_000)):
        if bps >= factor:
            value = bps / factor
            text = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{text} {unit}"
    return f"{bps} bps"


def _virtual(raw: Dict[str, Any]) -> bool:
    if _truthy(raw.get("virtual"), False):
        return True
    description = str(raw.get("description") or "").lower()
    return any(pattern in description for pattern in VIRTUAL_PATTERNS)


def _row(raw: Dict[str, Any]) -> Dict[str, Any]:
    state = _state(raw.get("status"))
    return {
        "name": _clip(raw.get("name")) or "(unnamed)",
        "description": _clip(raw.get("description")),
        "if_index": raw.get("if_index"),
        "status": raw.get("status"),
        "state": state,
        "problem": STATE_PROBLEMS.get(state, None if state == "up" else "state not recognised"),
        "virtual": _virtual(raw),
        "speed": _speed(raw.get("link_speed_bps")),
        "link_speed_bps": raw.get("link_speed_bps"),
        "mac": raw.get("mac") or None,
        "media_type": raw.get("media_type"),
        "driver_version": raw.get("driver_version") or None,
        "driver_date": (str(raw.get("driver_date") or "")[:10] or None),
    }


def _is_link_local(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_link_local
    except ValueError:
        return False


def _addresses(raw: Any) -> List[Dict[str, Any]]:
    """The configuration's IPv4 rows, with the null artefacts a missing answer leaves."""
    rows = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("address"):
            continue
        rows.append(
            {
                "address": item.get("address"),
                "prefix": item.get("prefix"),
                "origin": item.get("origin") or None,
                "link_local": _is_link_local(str(item.get("address"))),
            }
        )
    return rows


def _servers(raw: Any) -> List[str]:
    """DNS server addresses, without the null a missing answer leaves behind."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw else []
    return [str(item) for item in raw if item]


def win_adapter_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """Every visible network adapter, with the ones that have a problem called out."""
    args = args or {}
    query = str(args.get("query") or "").strip().lower()
    state_filter = str(args.get("state") or "").strip().lower()
    include_absent = _truthy(args.get("include_absent"), False)
    virtual_filter = args.get("virtual")
    virtual_wanted = None if virtual_filter is None else _truthy(virtual_filter, False)
    limit = _limit(args)

    try:
        raw = netpowershell.adapters()
    except netpowershell.PowerShellError as exc:
        return _fail(str(exc), code="adapters_unavailable")

    rows = [_row(item) for item in raw]
    visible = [row for row in rows if row["state"] != "not present" or include_absent]

    candidates = [
        row
        for row in visible
        if (not query or query in str(row.get("name") or "").lower()
            or query in str(row.get("description") or "").lower())
        and (not state_filter or row.get("state") == state_filter)
        and (virtual_wanted is None or row.get("virtual") is virtual_wanted)
    ]

    listed = candidates[:limit]
    up = [row["name"] for row in visible if row.get("state") == "up"]
    ghosts = len(rows) - len(visible)
    problems = [row for row in visible if row.get("problem")]

    notes = [
        f"{len(listed)} of {len(candidates)} matching adapter(s) listed, "
        f"{len(visible)} visible"
    ]
    if up:
        notes.append(f"up: {', '.join(up[:8])}")
    else:
        notes.append("no adapter is up: this machine has no network right now")
    if ghosts:
        notes.append(f"{ghosts} ghost adapter(s) whose hardware is not present are hidden; "
                     f"include_absent=true shows them")
    if problems:
        notes.append(f"{len(problems)} adapter(s) have a problem: "
                     + ", ".join(f"{row['name']} ({row['problem']})" for row in problems[:5]))
    if len(candidates) > len(listed):
        notes.append(f"stopped at limit={limit}; raise it or narrow the query")
    if not listed:
        notes.append("nothing matched; drop the query, the state or the virtual filter")
    if state_filter and state_filter not in KNOWN_STATES:
        notes.append(f"state is one of: {', '.join(sorted(KNOWN_STATES))}")

    return _ok(
        matched=len(listed),
        visible=len(visible),
        up_total=len(up),
        adapters=listed,
        notes=notes,
    )


def win_adapter_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One adapter in full: its addresses, gateways, DNS, driver, and a diagnosis."""
    args = args or {}
    requested = str(args.get("name") or "").strip()
    if not requested:
        return _fail("give the adapter's name, e.g. 'WLAN' or '以太网', or a substring "
                     "of its description", code="name_required")

    try:
        raw = netpowershell.adapters()
    except netpowershell.PowerShellError as exc:
        return _fail(str(exc), code="adapters_unavailable")

    lowered = requested.lower()
    present = [item for item in raw if _state(item.get("status")) != "not present"]
    ordered = present + [item for item in raw if item not in present]
    match = None
    for item in ordered:  # an exact name first, then a substring of name or description
        if str(item.get("name") or "").lower() == lowered:
            match = item
            break
    if match is None:
        for item in ordered:
            if lowered in str(item.get("name") or "").lower() or lowered in str(
                item.get("description") or ""
            ).lower():
                match = item
                break
    if match is None:
        token = lowered.split()[0] if lowered.split() else lowered
        near = [
            str(item.get("name"))
            for item in ordered
            if token in str(item.get("name") or "").lower()
            or token in str(item.get("description") or "").lower()
        ]
        return _fail(
            f"no adapter matches {requested}",
            code="not_found",
            suggestions=near[:5],
            hint="win_adapter_table lists every visible adapter",
        )

    row = _row(match)
    notes: List[str] = []

    ip: Dict[str, Any] | None = None
    config: Dict[str, Any] | None = None
    if_index = match.get("if_index")
    if isinstance(if_index, int):
        try:
            config = netpowershell.configuration(if_index)
        except netpowershell.PowerShellError as exc:
            notes.append(f"the IP configuration could not be read: {exc}")
    else:
        notes.append("the adapter has no interface index; the IP section is not shown")

    if config is not None:
        addresses = _addresses(config.get("ipv4"))
        dns4 = _servers(config.get("dns4"))
        dns6 = _servers(config.get("dns6"))
        ip = {
            "found": _truthy(config.get("found"), False),
            "ipv4": addresses,
            "ipv6": _servers(config.get("ipv6")),
            "gateway4": config.get("gateway4") or None,
            "gateway6": config.get("gateway6") or None,
            "dns4": dns4,
            "dns6": dns6,
        }
        _diagnose(row, ip, notes)

    return _ok(
        name=row["name"],
        description=row["description"],
        if_index=row["if_index"],
        status=row["status"],
        state=row["state"],
        virtual=row["virtual"],
        speed=row["speed"],
        mac=row["mac"],
        media_type=row["media_type"],
        driver={"version": row["driver_version"], "date": row["driver_date"]},
        ip=ip,
        notes=notes,
    )


def _diagnose(row: Dict[str, Any], ip: Dict[str, Any], notes: List[str]) -> None:
    """The connectivity verdicts a person needs, each one tied to a fact in the answer."""
    state = row.get("state")
    if state == "disabled":
        notes.append("this adapter is switched off; switch it on before looking further")
        return
    if state == "not present":
        notes.append("this adapter's hardware is not present; there is nothing to configure")
        return
    if state == "disconnected":
        notes.append("no medium: no cable is plugged in, or the wireless network is not joined")

    if not ip.get("found"):
        notes.append("IP is not bound to this adapter at all (usual for a virtual host adapter)")
        return

    addresses = ip.get("ipv4") or []
    if not addresses:
        if ip.get("ipv6"):
            notes.append("IPv6 only: this adapter has no IPv4 address")
        else:
            notes.append("no address at all: nothing has configured this adapter")
        if not (ip.get("dns4") or ip.get("dns6")):
            notes.append("no DNS server is known: names will not resolve")
        return

    link_local = [a for a in addresses if a.get("link_local")]
    working = [a for a in addresses if not a.get("link_local")]
    if link_local and not working:
        notes.append(
            "DHCP did not answer: Windows gave itself a link-local address (169.254.x.x), "
            "which reaches only its own subnet"
        )
        if ip.get("dns4"):
            notes.append(
                "the configured DNS servers cannot be reached through this address: "
                "there is no gateway to carry the question"
            )
        return

    if not ip.get("gateway4") and not ip.get("gateway6"):
        notes.append("has an address but no default gateway: it cannot leave its own subnet")
    if not (ip.get("dns4") or ip.get("dns6")):
        notes.append("no DNS server is known: names will not resolve")
    if not notes:
        notes.append(
            "connected: an address, a default gateway and DNS servers are all in place"
        )


__all__ = ["win_adapter_detail", "win_adapter_table"]
