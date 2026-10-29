"""Live tests: the real CIM, the real registry, the real event log, on this machine."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="live Windows services only"
)

from hermes_windows_services import svcquery, svcreg, tools  # noqa: E402


def test_cim_lists_the_machine_and_its_facts_hold_up():
    services = svcquery.services()
    assert len(services) > 80  # a bare Windows install already carries more than this
    for row in services[:20]:
        assert isinstance(row.get("name"), str) and row["name"]
        assert str(row.get("state")) in {
            "Running", "Stopped", "Paused", "Start Pending", "Stop Pending",
            "Continue Pending", "Pause Pending", "Unknown"}
        assert str(row.get("start")) in {"Boot", "System", "Auto", "Manual", "Disabled"}


def test_the_registry_dependency_cim_will_not_tell():
    # CIM's DependOnService is never populated; the registry is where it lives. The DNS
    # client waits for nsi on every Windows install.
    depends = svcreg.depends_on("dnscache")
    assert "nsi" in depends


def test_failure_actions_blob_decodes_on_a_real_service():
    policy = svcreg.failure_policy("wuauserv")
    if policy and policy.get("actions"):  # configurable, but factory Windows keeps it set
        assert policy["actions"][0]["type"] == "restart the service"
        assert policy["actions"][0]["after_seconds"] in {60.0, 60000.0 / 1000}


def test_table_lists_this_machine():
    answer = json.loads(tools.win_service_table({"limit": 15}))
    assert answer["ok"] is True
    assert len(answer["services"]) == 15
    assert any("registered" in note and "running" in note for note in answer["notes"])
    running = json.loads(tools.win_service_table({"state": "running"}))
    assert running["services"], "a machine running this test has services running"
    for row in running["services"]:
        assert str(row["state"]).lower() == "running"


def test_detail_of_a_real_service():
    answer = json.loads(tools.win_service_detail({"name": "wuauserv"}))
    assert answer["ok"] is True
    assert answer["name"] == "wuauserv"
    assert answer["binary"]["path"].lower().endswith(".exe")
    assert answer["depends_on"] == ["rpcss"] or isinstance(answer["depends_on"], list)
    assert isinstance(answer["recent_failures"], list)
