"""Live tests: the real firewall store, on this machine."""

from __future__ import annotations

import json
import time

import pytest

pytestmark = pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="live Windows registry only"
)

from hermes_windows_firewall import fwreg, tools  # noqa: E402


def test_the_real_store_is_large_and_wellformed():
    rules = fwreg.firewall_rules()
    assert len(rules) >= 300  # a real install carries hundreds of built-in rules
    for rule in rules:
        assert rule["id"]
        assert rule["fields"].get("action") in {"Allow", "Block"}
        assert rule["fields"].get("dir") in {"In", "Out"}
        assert rule["version"] and rule["version"].startswith("v2")


def test_built_in_names_resolve_on_this_machine():
    rules = fwreg.firewall_rules()
    indirect = [r for r in rules if str(r["fields"].get("name") or "").startswith("@")]
    assert indirect  # the built-in half of the store names itself indirectly
    resolved = [r for r in indirect if r["name_is_localized"]]
    assert resolved  # SHLoadIndirectString works in-process, unelevated


def test_the_three_profiles_are_present():
    profiles = {p["name"]: p for p in fwreg.profile_facts()}
    assert set(profiles) == {"domain", "public", "private"}
    assert profiles["public"]["display"] == "Public"
    # this class of machine writes EnableFirewall explicitly on every profile
    assert all(p["enabled"] is True for p in profiles.values())


def test_the_table_answers_fast():
    started = time.perf_counter()
    answer = json.loads(tools.win_firewall_table({}))
    elapsed = time.perf_counter() - started
    assert answer["ok"] is True
    assert len(answer["rules"]) == 100  # the default limit of a 700+-rule store
    assert len(answer["profiles"]) == 3
    assert answer["notes"]
    assert elapsed < 1.5  # one registry sweep plus cached resource lookups
    for row in answer["rules"]:
        assert row["id"] and row["action"] in {"Allow", "Block"}
        assert row["profiles"]


def test_the_filters_narrow_the_real_store():
    everything = json.loads(tools.win_firewall_table({"limit": 400}))
    outbound = json.loads(tools.win_firewall_table({"direction": "out", "limit": 400}))
    assert 0 < len(outbound["rules"]) < len(everything["rules"])
    assert all(row["direction"] == "Out" for row in outbound["rules"])

    active = json.loads(tools.win_firewall_table({"active": True, "limit": 400}))
    assert active["rules"] and all(row["active"] for row in active["rules"])

    svchost = json.loads(tools.win_firewall_table({"query": "svchost", "limit": 400}))
    assert svchost["rules"]  # a real store scopes its service rules this way


def test_the_detail_resolves_a_real_rule():
    table = json.loads(tools.win_firewall_table({}))
    rule_id = table["rules"][0]["id"]
    answer = json.loads(tools.win_firewall_detail({"name": rule_id}))
    assert answer["ok"] is True
    assert answer["id"] == rule_id
    assert answer["sentence"]
    missing = json.loads(tools.win_firewall_detail({"name": "no-such-rule-at-all"}))
    assert missing["ok"] is False and missing["code"] == "rule_not_found"
