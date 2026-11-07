"""The registry layer of Windows Firewall: the rule store and the three profiles.

Why the registry and not ``netsh advfirewall``: the firewall's own command
line labels its output in the machine's display language (a Chinese Windows
prints Chinese headers and value words), so parsing it means parsing a locale
that changes with the install. The registry is where the firewall service
keeps the store itself, and the data there is either enum-shaped (``Allow``,
``Block``, ``In``, ``TRUE``) or the user's own words -- neither translates.

Layout facts the reader relies on, all measured on a real Windows 11
(build 26100) machine:

- every rule is one ``REG_SZ`` value under
  ``HKLM\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\
  FirewallPolicy\\FirewallRules``: the value's *name* is the rule id
  (``NETDIS-SSDPSrv-Out-UDP-Active``), the data a pipe-separated
  ``v2.33|Action=Allow|Active=TRUE|Dir=Out|Protocol=17|...`` string;
  795 rules on the writing machine, all ``v2.33``;
- keys the parser does not model appear in the wild (``TTK2_22`` is on real
  machines) and are kept verbatim instead of dropped;
- built-in rules name themselves indirectly -- ``@FirewallAPI.dll,-32765`` --
  and the localized words live in the resource, not in the registry;
  ``SHLoadIndirectString`` resolves them in-process, and when it cannot the
  raw reference is reported as-is;
- the three profile keys sit *directly* under ``FirewallPolicy`` on current
  builds (``DomainProfile``, ``PublicProfile``, ``StandardProfile`` -- the
  last is what the UI calls Private). A profile key carries only what policy
  wrote: on the writing machine just ``EnableFirewall`` and
  ``DisableNotifications``. Values it leaves absent have documented built-in
  defaults (firewall on, inbound blocked, outbound allowed) -- the tools
  report what the registry says and attribute the rest as builtin defaults,
  never an invented number;
- the optional per-user rule store
  (``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\FirewallRules``) is
  absent on current builds: swept, reported empty, never an error.
"""

from __future__ import annotations

import ctypes
from typing import Any, Callable

try:
    import winreg
except ImportError:  # not Windows: the plugin is Windows-only and says so when asked
    winreg = None

POLICY_PATH = r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy"
RULES_PATH = POLICY_PATH + r"\FirewallRules"
USER_RULES_PATH = r"Software\Microsoft\Windows\CurrentVersion\FirewallRules"

# (key name, wire name) -- StandardProfile is what every UI calls Private
PROFILE_KEYS = (
    ("DomainProfile", "domain"),
    ("PublicProfile", "public"),
    ("StandardProfile", "private"),
)
PROFILE_DISPLAY = {"domain": "Domain", "public": "Public", "private": "Private"}

# the keys a v2.33 rule string carries that the tools model by name; anything
# else survives in ``extra``
KNOWN_RULE_KEYS = frozenset({
    "action", "active", "dir", "protocol", "profile",
    "lport", "rport", "lportran", "portran",
    "app", "svc", "name", "desc", "embedctxt", "group", "edge",
    "la4", "la6", "ra4", "ra6",
})

PROTOCOL_NAMES = {
    "1": "ICMPv4", "6": "TCP", "17": "UDP",
    "47": "GRE", "50": "ESP", "51": "AH", "58": "ICMPv6",
}

# profile values with a meaning the tools surface by name; the rest stay
# verbatim under ``extra``
PROFILE_VALUE_MEANINGS = {
    "enablefirewall": ("enabled", "bool"),
    "disablenotifications": ("notifications_disabled", "bool"),
    "defaultinboundaction": ("default_inbound", "action"),
    "defaultoutboundaction": ("default_outbound", "action"),
    "allowinboundrules": ("inbound_rules_allowed", "bool"),
    "donotallowexceptions": ("exceptions_blocked", "bool"),
    "disableunicastresponsestomulticast": ("unicast_responses_disabled", "bool"),
}

ACTION_NAMES = {"1": "Allow", "2": "Block"}


class RegistryUnavailable(Exception):
    """The firewall's registry store exists only on Windows (or could not be opened)."""


def _hive(which: str):
    if winreg is None:
        raise RegistryUnavailable("the firewall's registry store exists only on Windows")
    return winreg.HKEY_CURRENT_USER if which == "hkcu" else winreg.HKEY_LOCAL_MACHINE


def _values(which: str, path: str, opener: Callable | None = None) -> dict[str, Any]:
    """Every value under one key; a key that does not exist is empty, never an error."""
    if winreg is None:
        raise RegistryUnavailable("the firewall's registry store exists only on Windows")
    open_key = opener or winreg.OpenKey
    out: dict[str, Any] = {}
    try:
        with open_key(_hive(which), path) as key:
            index = 0
            while True:
                try:
                    name, data, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                out[str(name)] = data
                index += 1
    except OSError:
        return {}
    return out


def _shload(text: str) -> str | None:
    """One ``@dll,-id`` reference resolved in-process; None when it will not."""
    buffer = ctypes.create_unicode_buffer(1024)
    result = ctypes.windll.shlwapi.SHLoadIndirectString(text, buffer, 1024, None)
    return buffer.value if result == 0 and buffer.value else None


def load_display(text: Any, loader: Callable | None = None, cache: dict | None = None) -> Any:
    """A rule's display words: indirect references resolved, plain text verbatim.

    Resolution is best-effort by design -- the raw ``@dll,-id`` reference is
    always a complete answer, and the localized words are a courtesy the
    machine's own resource loader provides.
    """
    if not isinstance(text, str) or not text.startswith("@"):
        return text
    if cache is not None and text in cache:
        return cache[text]
    fetch = loader or _shload
    try:
        resolved = fetch(text)
    except Exception:
        resolved = None
    answer = resolved if isinstance(resolved, str) and resolved else text
    if cache is not None:
        cache[text] = answer
    return answer


def parse_rule(rule_id: str, raw: Any) -> dict[str, Any]:
    """One ``v2.33|Action=Allow|...`` string into facts; unknown keys kept."""
    parts = [part for part in str(raw).split("|") if part]
    version = parts[0] if parts and parts[0].lower().startswith("v") else None
    fields: dict[str, str] = {}
    for part in parts[1:] if version else parts:
        if "=" not in part:
            continue  # a stray token with no '=' has nowhere honest to go
        key, value = part.split("=", 1)
        fields[key.strip().lower()] = value
    known: dict[str, str] = {}
    extra: dict[str, str] = {}
    for key, value in fields.items():
        (known if key in KNOWN_RULE_KEYS else extra)[key] = value
    return {"id": rule_id, "version": version, "fields": known, "extra": extra}


def _rule(rule_id: str, raw: Any, loader: Callable | None = None,
          cache: dict | None = None) -> dict[str, Any]:
    facts = parse_rule(rule_id, raw)
    # name, description and the embedding group resolve through the same
    # best-effort loader, so every display word a tool ever shows came through
    # one injectable path
    for out_name, key in (("name", "name"), ("desc", "desc"), ("group", "embedctxt")):
        ref = facts["fields"].get(key)
        facts[out_name] = load_display(ref, loader, cache) if ref else None
    name_ref = facts["fields"].get("name")
    facts["name_is_localized"] = bool(name_ref and facts["name"] != name_ref)
    return facts


def firewall_rules(opener: Callable | None = None,
                   loader: Callable | None = None) -> list[dict[str, Any]]:
    """Every rule from the machine store plus the per-user store when it exists."""
    if winreg is None:
        raise RegistryUnavailable("the firewall's registry store exists only on Windows")
    cache: dict = {}
    rules: list[dict[str, Any]] = []
    for rule_id, raw in _values("hklm", RULES_PATH, opener).items():
        rule = _rule(rule_id, raw, loader, cache)
        rule["source"] = "machine"
        rules.append(rule)
    for rule_id, raw in _values("hkcu", USER_RULES_PATH, opener).items():
        rule = _rule(rule_id, raw, loader, cache)
        rule["source"] = "user"
        rules.append(rule)
    return rules


def profile_facts(opener: Callable | None = None) -> list[dict[str, Any]]:
    """The three profile switches, each with what the registry actually wrote."""
    if winreg is None:
        raise RegistryUnavailable("the firewall's registry store exists only on Windows")
    profiles: list[dict[str, Any]] = []
    for key_name, wire in PROFILE_KEYS:
        raw = _values("hklm", POLICY_PATH + "\\" + key_name, opener)
        # every modelled value starts as None -- "the registry did not write
        # it" -- and only what the key really carries is filled in
        facts: dict[str, Any] = {
            out_name: None for out_name in {pair[0] for pair in PROFILE_VALUE_MEANINGS.values()}
        }
        facts.update({
            "name": wire,
            "display": PROFILE_DISPLAY[wire],
            "present": True,
            "registry_values": sorted(raw),
        })
        for value_name, data in raw.items():
            mapped = PROFILE_VALUE_MEANINGS.get(value_name.lower())
            if mapped is None:
                facts.setdefault("extra", {})[value_name] = data
                continue
            out_name, kind = mapped
            if kind == "bool":
                if isinstance(data, int):
                    facts[out_name] = bool(data)
                else:
                    facts[out_name] = str(data).strip() not in ("", "0")
            else:
                facts[out_name] = ACTION_NAMES.get(str(data).strip(), str(data))
        profiles.append(facts)
    return profiles


__all__ = [
    "ACTION_NAMES", "PROFILE_KEYS", "PROTOCOL_NAMES", "RegistryUnavailable",
    "firewall_rules", "load_display", "parse_rule", "profile_facts",
]
