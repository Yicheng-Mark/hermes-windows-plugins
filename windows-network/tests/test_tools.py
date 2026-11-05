"""The two tools over answers a test owns (hermes_windows_network/tools.py).

The fixture rows are shaped like this machine's real answers: a healthy wireless
adapter, an ethernet adapter sitting on a link-local address with no cable, a
Hyper-V virtual adapter IP is not bound to, the ghost of a radio that is gone,
and a Bluetooth adapter that was switched off.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from hermes_windows_network import netpowershell, tools

ADAPTERS = [
    {
        "name": "WLAN",
        "description": "Intel(R) Wi-Fi 7 BE201 320MHz",
        "if_index": 14,
        "status": "Up",
        "mac": "C8-95-CE-CD-5F-4B",
        "link_speed_bps": 526500000,
        "media_type": "Native 802.11",
        "virtual": False,
        "driver_version": "23.160.0.4",
        "driver_date": "2025-07-21T00:00:00.0000000",
    },
    {
        "name": "WLAN 2",
        "description": "Intel(R) Wi-Fi 7 BE201 320MHz",
        "if_index": 12,
        "status": "Not Present",
        "mac": "",
        "link_speed_bps": 0,
        "media_type": "Native 802.11",
        "virtual": False,
        "driver_version": "23.160.0.4",
        "driver_date": "2025-07-21T00:00:00.0000000",
    },
    {
        "name": "以太网",
        "description": "Intel(R) Ethernet Connection (24) I219-V",
        "if_index": 9,
        "status": "Disconnected",
        "mac": "38-A7-46-43-71-76",
        "link_speed_bps": None,
        "media_type": "802.3",
        "virtual": False,
        "driver_version": "20.0.3.9",
        "driver_date": "2025-04-08T00:00:00.0000000",
    },
    {
        "name": "vEthernet (FSE HostVnic)",
        "description": "Hyper-V Virtual Ethernet Container Adapter",
        "if_index": 47,
        "status": "Up",
        "mac": "00-15-5D-29-36-7D",
        "link_speed_bps": 10000000000,
        "media_type": "802.3",
        "virtual": True,
        "driver_version": None,
        "driver_date": "",
    },
    {
        "name": "蓝牙",
        "description": "Intel(R) Wireless Bluetooth(R)",
        "if_index": 22,
        "status": "Disabled",
        "mac": "",
        "link_speed_bps": 0,
        "media_type": "Native 802.11",
        "virtual": False,
        "driver_version": "23.160.0.4",
        "driver_date": "2025-07-21T00:00:00.0000000",
    },
    {
        "name": "TAP1",
        "description": "TAP-Windows Adapter V9",
        "if_index": 31,
        "status": "Disconnected",
        "mac": "00-FF-31-AA-BB-CC",
        "link_speed_bps": None,
        "media_type": "802.3",
        "virtual": False,  # the flag is missing; the description has to carry it
        "driver_version": "9.0.0.24",
        "driver_date": "2019-06-10T00:00:00.0000000",
    },
]

CONFIGS: Dict[int, Dict[str, Any]] = {
    14: {
        "found": True,
        "ipv4": [{"address": "192.168.0.200", "prefix": 24, "origin": "Dhcp"}],
        "ipv6": ["fe80::1234"],
        "gateway4": "192.168.0.1",
        "gateway6": None,
        "dns4": ["223.5.5.5", "119.29.29.29"],
        "dns6": [],
    },
    9: {  # no cable, and a link-local address with a leftover static DNS
        "found": True,
        "ipv4": [{"address": "169.254.57.204", "prefix": 16, "origin": "WellKnown"}],
        "ipv6": [],
        "gateway4": None,
        "gateway6": None,
        "dns4": ["192.168.3.1"],
        "dns6": [],
    },
    47: {  # IP is not bound: the missing answer leaves null artefacts behind
        "found": False,
        "ipv4": [{"address": None, "prefix": None, "origin": ""}],
        "ipv6": [],
        "gateway4": None,
        "gateway6": None,
        "dns4": [None],
        "dns6": [None],
    },
}


@pytest.fixture()
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netpowershell, "adapters", lambda **_k: [dict(r) for r in ADAPTERS])
    monkeypatch.setattr(
        netpowershell,
        "configuration",
        lambda idx, **_k: CONFIGS.get(
            idx,
            {"found": False, "ipv4": [], "ipv6": [], "gateway4": None,
             "gateway6": None, "dns4": [], "dns6": []},
        ),
    )


def test_the_listing_hides_ghosts_and_names_the_healthy(live: None) -> None:
    result = json.loads(tools.win_adapter_table({}))
    assert result["ok"] is True
    names = [row["name"] for row in result["adapters"]]
    assert "WLAN 2" not in names
    assert names == ["WLAN", "以太网", "vEthernet (FSE HostVnic)", "蓝牙", "TAP1"]
    assert result["visible"] == 5
    assert result["up_total"] == 2
    assert any("up: WLAN" in note for note in result["notes"])
    assert any("1 ghost adapter" in note for note in result["notes"])


def test_include_absent_brings_the_ghost_back(live: None) -> None:
    result = json.loads(tools.win_adapter_table({"include_absent": True}))
    states = {row["name"]: row["state"] for row in result["adapters"]}
    assert states["WLAN 2"] == "not present"


def test_a_state_filter_is_applied_as_given(live: None) -> None:
    result = json.loads(tools.win_adapter_table({"state": "disabled"}))
    assert [row["name"] for row in result["adapters"]] == ["蓝牙"]
    assert result["adapters"][0]["problem"] == "switched off on purpose; nothing is broken"


def test_a_query_matches_the_name_or_the_description(live: None) -> None:
    by_name = json.loads(tools.win_adapter_table({"query": "以太"}))
    assert [row["name"] for row in by_name["adapters"]] == ["以太网"]
    by_description = json.loads(tools.win_adapter_table({"query": "hyper-v"}))
    assert [row["name"] for row in by_description["adapters"]] == [
        "vEthernet (FSE HostVnic)"
    ]


def test_the_virtual_filter_splits_physical_from_virtual(live: None) -> None:
    virtual = json.loads(tools.win_adapter_table({"virtual": True}))
    assert [row["name"] for row in virtual["adapters"]] == [
        "vEthernet (FSE HostVnic)",
        "TAP1",  # caught by its description, not by its missing flag
    ]
    physical = json.loads(tools.win_adapter_table({"virtual": False}))
    assert "vEthernet (FSE HostVnic)" not in {row["name"] for row in physical["adapters"]}
    assert "TAP1" not in {row["name"] for row in physical["adapters"]}


def test_a_limit_stops_the_listing_and_says_so(live: None) -> None:
    result = json.loads(tools.win_adapter_table({"limit": 2}))
    assert len(result["adapters"]) == 2
    assert any("stopped at limit" in note for note in result["notes"])


def test_nothing_matched_says_how_to_widen(live: None) -> None:
    result = json.loads(tools.win_adapter_table({"query": "nope"}))
    assert result["matched"] == 0
    assert any("nothing matched" in note for note in result["notes"])


def test_a_machine_with_no_adapter_up_says_so(live: None, monkeypatch: pytest.MonkeyPatch) -> None:
    down = [dict(row) for row in ADAPTERS if row["status"] != "Up"]
    monkeypatch.setattr(netpowershell, "adapters", lambda **_k: down)
    result = json.loads(tools.win_adapter_table({}))
    assert any("no adapter is up" in note for note in result["notes"])


def test_speeds_are_numbers_in_a_persons_words(live: None) -> None:
    row = {row["name"]: row for row in json.loads(tools.win_adapter_table({}))["adapters"]}
    assert row["WLAN"]["speed"] == "526.5 Mbps"
    assert row["vEthernet (FSE HostVnic)"]["speed"] == "10 Gbps"
    assert row["以太网"]["speed"] is None  # no medium, not zero
    assert row["以太网"]["driver_date"] == "2025-04-08"


def test_a_healthy_adapter_is_diagnosed_as_connected(live: None) -> None:
    result = json.loads(tools.win_adapter_detail({"name": "WLAN"}))
    assert result["ok"] is True
    assert result["state"] == "up"
    assert result["ip"]["ipv4"][0]["address"] == "192.168.0.200"
    assert result["ip"]["ipv4"][0]["origin"] == "Dhcp"
    assert result["ip"]["gateway4"] == "192.168.0.1"
    assert result["ip"]["dns4"] == ["223.5.5.5", "119.29.29.29"]
    assert result["notes"] == [
        "connected: an address, a default gateway and DNS servers are all in place"
    ]


def test_a_link_local_address_names_dhcp_and_the_stranded_dns(live: None) -> None:
    result = json.loads(tools.win_adapter_detail({"name": "以太网"}))
    assert result["ok"] is True
    assert result["ip"]["ipv4"][0]["link_local"] is True
    assert result["notes"][0] == (
        "no medium: no cable is plugged in, or the wireless network is not joined"
    )
    assert any("DHCP did not answer" in note for note in result["notes"])
    assert any("cannot be reached through this address" in note for note in result["notes"])


def test_an_adapter_ip_is_not_bound_to_says_so_without_nulls(live: None) -> None:
    result = json.loads(tools.win_adapter_detail({"name": "vethernet"}))
    assert result["ok"] is True  # found by the description, case-insensitively
    assert result["virtual"] is True
    assert result["ip"]["found"] is False
    assert result["ip"]["ipv4"] == []  # the null artefact is dropped, not shown
    assert result["ip"]["dns4"] == []
    assert any("IP is not bound" in note for note in result["notes"])


def test_a_disabled_adapter_stops_at_the_verdict(live: None) -> None:
    result = json.loads(tools.win_adapter_detail({"name": "蓝牙"}))
    assert result["state"] == "disabled"
    assert result["notes"] == [
        "this adapter is switched off; switch it on before looking further"
    ]


def test_an_exact_name_wins_over_a_substring(live: None) -> None:
    result = json.loads(tools.win_adapter_detail({"name": "wlan"}))
    assert result["name"] == "WLAN"  # WLAN 2 is a ghost, and substring only breaks ties


def test_a_name_that_is_not_there_says_what_is_close(live: None) -> None:
    result = json.loads(tools.win_adapter_detail({"name": "以太网 2"}))
    assert result["ok"] is False
    assert result["code"] == "not_found"
    assert result["suggestions"] == ["以太网"]


def test_a_detail_without_a_name_is_refused(live: None) -> None:
    result = json.loads(tools.win_adapter_detail({}))
    assert result["ok"] is False
    assert result["code"] == "name_required"


def test_a_configuration_that_cannot_be_read_still_answers(
    live: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(idx: int, **_k: Any) -> Dict[str, Any]:
        raise netpowershell.PowerShellError("PowerShell did not answer within 60s")

    monkeypatch.setattr(netpowershell, "configuration", refuse)
    result = json.loads(tools.win_adapter_detail({"name": "WLAN"}))
    assert result["ok"] is True
    assert result["state"] == "up"  # what the listing knows is still there
    assert result["ip"] is None
    assert any("could not be read" in note for note in result["notes"])


def test_powershell_that_does_not_answer_is_an_error_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**_kwargs: Any) -> list[dict[str, Any]]:
        raise netpowershell.PowerShellError("PowerShell did not answer within 60s")

    monkeypatch.setattr(netpowershell, "adapters", refuse)
    for answer in (tools.win_adapter_table({}), tools.win_adapter_detail({"name": "WLAN"})):
        result = json.loads(answer)
        assert result["ok"] is False
        assert result["code"] == "adapters_unavailable"
