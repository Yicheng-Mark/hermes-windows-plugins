"""Unit tests: every layer with fakes, no real registry anywhere."""

from __future__ import annotations

import json

import pytest

from hermes_windows_firewall import fwreg, tools


# --- fakes --------------------------------------------------------------------

NETDIS = (
    "v2.33|Action=Allow|Active=TRUE|Dir=Out|Protocol=17|RPort=1900|"
    "RA4=LocalSubnet|RA6=LocalSubnet|"
    "App=%SystemRoot%\\system32\\svchost.exe|Svc=Ssdpsrv|"
    "Name=@FirewallAPI.dll,-32757|Desc=@FirewallAPI.dll,-32760|"
    "EmbedCtxt=@FirewallAPI.dll,-32752|"
)
MYAPP = (
    "v2.33|Action=Allow|Active=FALSE|Dir=In|Protocol=6|LPort=8080|"
    "App=C:\\Program Files\\MyApp\\server.exe|Name=My App Web|Desc=Serves the web UI|"
    "Profile=Domain,Private|EmbedCtxt=My App|"
)
BLOCK_TELNET = (
    "v2.33|Action=Block|Active=TRUE|Dir=In|Protocol=6|LPort=23|RA4=*|"
    "App=Any|Name=Block Telnet|"
)
WFD_PRINT = (
    "v2.33|Action=Allow|Active=TRUE|Dir=Out|Protocol=6|TTK2_22=WFDPrint|"
    "Profile=Public|RPort=1024-65535|Name=@FirewallAPI.dll,-36858|"
)
GRE_TUNNEL = "v2.33|Action=Allow|Active=TRUE|Dir=Out|Protocol=47|Name=GRE tunnel|Edge=DeferToUser|"
BARE_RULE = "v2.33|Name=Bare rule|"

MACHINE_RULES = {
    "NETDIS-SSDPSrv-Out-UDP-Active": NETDIS,
    "MyApp-Web-In-TCP": MYAPP,
    "Block-Telnet-In": BLOCK_TELNET,
    "WFD-Print-Out": WFD_PRINT,
    "GRE-Tunnel": GRE_TUNNEL,
    "Bare-Rule": BARE_RULE,
}

PROFILE_STORE = {
    "DomainProfile": {"EnableFirewall": (1, 4), "DefaultInboundAction": (2, 4)},
    "PublicProfile": {"EnableFirewall": (0, 4), "DisableNotifications": (1, 4),
                      "SomeFutureValue": (5, 4)},
    "StandardProfile": {},  # present but silent: builtin defaults apply
}

# the resource words a real machine would give the two indirect refs the store uses
DISPLAY_WORDS = {
    "@FirewallAPI.dll,-32757": "SSDP 发现",
    "@FirewallAPI.dll,-32752": "网络发现",
}


class _FakeKey:
    def __init__(self, values):
        self._values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _open(table):
    """A winreg.OpenKey stand-in: one leaf key per registered path."""

    def open_key(hive, path):
        node = table.get((hive, str(path)))
        if node is None:
            raise OSError("no such key")
        return _FakeKey(node)

    return open_key


def _enum_value(key, index):
    items = sorted(key._values)
    if index >= len(items):
        raise OSError("no more values")
    name = items[index]
    data, kind = key._values[name]
    return name, data, kind


@pytest.fixture()
def store(monkeypatch):
    """The registry layer runs its real code over a fake value store."""
    monkeypatch.setattr(fwreg, "_hive", lambda which: which)
    monkeypatch.setattr(fwreg.winreg, "EnumValue", _enum_value)

    table = {
        ("hklm", fwreg.RULES_PATH): {name: (data, 1) for name, data in MACHINE_RULES.items()},
        # the per-user store is deliberately absent, as on current builds
    }
    for name, values in PROFILE_STORE.items():
        table[("hklm", fwreg.POLICY_PATH + "\\" + name)] = values
    bound_open = _open(table)

    def fake_loader(ref):
        return DISPLAY_WORDS.get(ref)

    real_rules = fwreg.firewall_rules
    real_profiles = fwreg.profile_facts
    monkeypatch.setattr(
        fwreg, "firewall_rules",
        lambda opener=None, loader=None: real_rules(opener=bound_open, loader=loader or fake_loader))
    monkeypatch.setattr(
        fwreg, "profile_facts",
        lambda opener=None: real_profiles(opener=bound_open))
    return {"table": table, "loader": fake_loader, "open": bound_open}


def _load(text: str) -> dict:
    return json.loads(text)


# --- the parser ---------------------------------------------------------------

def test_parse_rule_models_known_keys_and_keeps_the_rest():
    rule = fwreg.parse_rule("NETDIS", NETDIS)
    assert rule["version"] == "v2.33"
    fields = rule["fields"]
    assert fields["action"] == "Allow" and fields["dir"] == "Out"
    assert fields["rport"] == "1900" and fields["svc"] == "Ssdpsrv"
    assert rule["extra"] == {}
    wfd = fwreg.parse_rule("WFD", WFD_PRINT)
    assert wfd["extra"] == {"ttk2_22": "WFDPrint"}  # in-the-wild unknown key kept
    assert wfd["fields"]["rport"] == "1024-65535"


def test_parse_rule_without_version_and_with_stray_tokens():
    rule = fwreg.parse_rule("odd", "Action=Allow|garbage|Dir=In")
    assert rule["version"] is None
    assert rule["fields"] == {"action": "Allow", "dir": "In"}  # stray token dropped


# --- the display-word resolver --------------------------------------------------

def test_load_display_plain_indirect_and_failing():
    calls = []

    def counting(ref):
        calls.append(ref)
        return DISPLAY_WORDS.get(ref)

    assert fwreg.load_display("Plain Name", counting) == "Plain Name"  # not indirect
    assert fwreg.load_display("@FirewallAPI.dll,-32757", counting) == "SSDP 发现"
    assert fwreg.load_display("@FirewallAPI.dll,-99999", counting) == "@FirewallAPI.dll,-99999"

    cache: dict = {}
    fwreg.load_display("@FirewallAPI.dll,-32757", counting, cache)
    fwreg.load_display("@FirewallAPI.dll,-32757", counting, cache)
    assert len(calls) == 3  # the cached second ask did not reach the loader


def test_rules_resolve_names_through_the_loader(store):
    rules = fwreg.firewall_rules()
    by_id = {rule["id"]: rule for rule in rules}
    netdis = by_id["NETDIS-SSDPSrv-Out-UDP-Active"]
    assert netdis["name"] == "SSDP 发现"
    assert netdis["name_is_localized"] is True
    wfd = by_id["WFD-Print-Out"]
    assert wfd["name"] == "@FirewallAPI.dll,-36858"  # loader misses: raw ref, the honest answer
    assert wfd["name_is_localized"] is False
    assert by_id["MyApp-Web-In-TCP"]["name"] == "My App Web"  # third-party words verbatim


def test_both_stores_read_and_absent_user_store_is_empty(store):
    rules = fwreg.firewall_rules()
    assert len(rules) == len(MACHINE_RULES)
    assert {rule["source"] for rule in rules} == {"machine"}


# --- the profiles ---------------------------------------------------------------

def test_profiles_reading_and_builtins_left_null(store):
    profiles = {p["name"]: p for p in fwreg.profile_facts()}
    assert set(profiles) == {"domain", "public", "private"}
    assert profiles["domain"]["enabled"] is True
    assert profiles["domain"]["default_inbound"] == "Block"  # action enum 1/2 read
    assert profiles["public"]["enabled"] is False
    assert profiles["public"]["notifications_disabled"] is True
    assert profiles["public"]["extra"] == {"SomeFutureValue": 5}  # unknown value verbatim
    private = profiles["private"]
    assert private["present"] is True
    assert private["enabled"] is None and private["default_inbound"] is None


def test_without_winreg_the_store_answers_an_error(monkeypatch):
    monkeypatch.setattr(fwreg, "winreg", None)
    with pytest.raises(fwreg.RegistryUnavailable):
        fwreg.firewall_rules()
    with pytest.raises(fwreg.RegistryUnavailable):
        fwreg.profile_facts()


def test_module_imports_where_winreg_does_not_exist(monkeypatch):
    """The catalog's Linux validator imports the plugin with no winreg present:
    nothing may touch winreg at import time, and a missing registry is a raised,
    answerable error, not a crash."""
    import importlib
    import sys

    class _Blocked:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "winreg":
                raise ImportError("blocked: simulating a non-Windows import")
            return None

    blocker = _Blocked()
    saved = sys.modules.pop("winreg", None)
    sys.meta_path.insert(0, blocker)
    try:
        importlib.reload(fwreg)
        assert fwreg.winreg is None
        with pytest.raises(fwreg.RegistryUnavailable):
            fwreg.firewall_rules()
        tools_answer = tools.win_firewall_table({})
        assert _load(tools_answer)["code"] == "registry_unavailable"
    finally:
        sys.meta_path.remove(blocker)
        if saved is not None:
            sys.modules["winreg"] = saved
        importlib.reload(fwreg)


# --- the table ------------------------------------------------------------------

def test_table_lists_profiles_and_rules_with_notes(store):
    answer = _load(tools.win_firewall_table({}))
    assert answer["ok"] is True
    assert [p["name"] for p in answer["profiles"]] == ["domain", "public", "private"]
    assert answer["profiles"][0]["enabled"] is True
    assert answer["profiles"][1]["enabled"] is False
    ids = {row["id"] for row in answer["rules"]}
    assert ids == set(MACHINE_RULES)
    joined = " ".join(answer["notes"])
    assert "6 in the store" in joined
    assert "SWITCHED OFF for: Public" in joined
    assert "switched off" in joined  # the inactive-rule count
    assert "no per-user rule store" in joined
    assert "builtin default" in joined  # the private profile's nulls explained


def test_table_row_shape(store):
    answer = _load(tools.win_firewall_table({"query": "netdis"}))
    row = answer["rules"][0]
    assert row["name"] == "SSDP 发现" and row["name_is_localized"] is True
    assert row["action"] == "Allow" and row["direction"] == "Out"
    assert row["protocol"] == "UDP" and row["protocol_number"] == 17
    assert row["remote_ports"] == "1900"
    assert row["program"].endswith("svchost.exe")  # %SystemRoot% expanded
    assert row["service"] == "Ssdpsrv"
    assert row["profiles"] == ["any"]


def test_table_filters(store):
    by_dir = _load(tools.win_firewall_table({"direction": "in"}))
    assert {r["id"] for r in by_dir["rules"]} == {"MyApp-Web-In-TCP", "Block-Telnet-In"}

    by_profile = _load(tools.win_firewall_table({"profile": "public"}))
    assert {r["id"] for r in by_profile["rules"]} == {"WFD-Print-Out"}

    inactive = _load(tools.win_firewall_table({"active": False}))
    assert {r["id"] for r in inactive["rules"]} == {"MyApp-Web-In-TCP"}

    by_program = _load(tools.win_firewall_table({"query": "svchost"}))
    assert {r["id"] for r in by_program["rules"]} == {"NETDIS-SSDPSrv-Out-UDP-Active"}

    by_name = _load(tools.win_firewall_table({"query": "telnet"}))
    assert {r["id"] for r in by_name["rules"]} == {"Block-Telnet-In"}

    dual = _load(tools.win_firewall_table({"query": "my app web"}))
    assert dual["rules"][0]["profiles"] == ["domain", "private"]

    limited = _load(tools.win_firewall_table({"limit": 2}))
    assert len(limited["rules"]) == 2
    assert any("stopped at limit" in note for note in limited["notes"])


def test_table_bad_filters_are_noted(store):
    bad_dir = _load(tools.win_firewall_table({"direction": "sideways"}))
    assert bad_dir["rules"] == []
    assert any("direction is one of" in note for note in bad_dir["notes"])
    bad_profile = _load(tools.win_firewall_table({"profile": "guest"}))
    assert any("profile is one of" in note for note in bad_profile["notes"])


# --- the detail -----------------------------------------------------------------

def test_detail_reads_one_rule_in_full(store):
    answer = _load(tools.win_firewall_detail({"name": "netdis-ssdpsrv-out-udp-active"}))
    assert answer["ok"] is True
    assert answer["sentence"].startswith("allows outbound UDP")
    assert "1900" in answer["sentence"] and "Ssdpsrv" in answer["sentence"]
    assert answer["remote_addresses"] == [
        {"ip": "IPv4", "scope": "the local subnet"},
        {"ip": "IPv6", "scope": "the local subnet"},
    ]
    assert answer["program"]["path"].endswith("svchost.exe")
    assert answer["program"]["ref"] == "%SystemRoot%\\system32\\svchost.exe"
    assert answer["group"] == "网络发现"
    assert answer["description"] == "@FirewallAPI.dll,-32760"  # loader miss: raw ref
    assert answer["store_version"] == "v2.33"
    assert any("service is the actual actor" in note for note in answer["notes"])


def test_detail_notes_matrix(store):
    switched_off = _load(tools.win_firewall_detail({"name": "myapp"}))
    assert "SWITCHED OFF" in switched_off["sentence"]
    assert any("matches nothing" in note for note in switched_off["notes"])

    edge = _load(tools.win_firewall_detail({"name": "gre"}))
    assert edge["protocol"] == "GRE" and edge["protocol_number"] == 47
    assert any("edge traversal" in note for note in edge["notes"])

    bare = _load(tools.win_firewall_detail({"name": "bare rule"}))
    assert any("not scoped" in note for note in bare["notes"])


def test_detail_match_and_miss(store):
    by_name = _load(tools.win_firewall_detail({"name": "block telnet"}))
    assert by_name["ok"] is True
    assert by_name["sentence"].startswith("blocks inbound TCP")
    assert "any address" in by_name["sentence"] and "any program" in by_name["sentence"]

    no_name = _load(tools.win_firewall_detail({}))
    assert no_name["code"] == "name_required"
    missing = _load(tools.win_firewall_detail({"name": "does-not-exist"}))
    assert missing["ok"] is False and missing["code"] == "rule_not_found"
    assert missing["suggestions"] is not None
