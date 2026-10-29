"""Live tests: the real device tree and driver table, on this machine."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="live Windows devices only"
)

from hermes_windows_devices import devquery, tools  # noqa: E402


def test_the_tree_lists_and_the_facts_hold_up():
    devices = devquery.devices()
    assert len(devices) > 80
    present = [d for d in devices if d.get("present")]
    assert len(present) >= 80  # a real machine carries more than this
    for row in present[:20]:
        assert isinstance(row.get("code"), int)
        assert str(row.get("device_id")).count("\\") >= 1


def test_the_driver_table_carries_versions():
    drivers = devquery.drivers()
    assert len(drivers) > 50
    with_signer = [d for d in drivers if d.get("signer")]
    assert len(with_signer) > 30  # a healthy install signs nearly everything
    assert any(d.get("version") for d in drivers)


def test_table_lists_this_machine():
    answer = json.loads(tools.win_device_table({"limit": 20}))
    assert answer["ok"] is True
    assert len(answer["devices"]) == 20
    assert any("largest classes" in note for note in answer["notes"])


def test_detail_of_a_real_device():
    table = json.loads(tools.win_device_table({"class": "net", "limit": 1}))
    if not table["devices"]:
        pytest.skip("no network device on this machine")
    target = table["devices"][0]
    answer = json.loads(tools.win_device_detail({"name": target["device_id"]}))
    assert answer["ok"] is True
    assert answer["driver"]["version"]  # a network device always has a driver
    assert answer["driver"]["signed"] is True
