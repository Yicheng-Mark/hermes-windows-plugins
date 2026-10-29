"""Unit tests: the tools over faked CIM answers, no PowerShell."""

from __future__ import annotations

import json

import pytest

from hermes_windows_devices import codes, tools


DEVICES = [
    {"name": "Intel(R) Wireless-AC", "class": "Net", "status": "OK", "code": 0,
     "manufacturer": "Intel", "device_id": r"PCI\VEN_8086&DEV_2723&SUBSYS_00348086", "present": True},
    {"name": "未知设备", "class": "System", "status": "Error", "code": 28,
     "manufacturer": None, "device_id": r"ROOT\LENOVO_VIRTUAL_BUS\0000", "present": True},
    {"name": "旧打印机 (历史)", "class": "Printer", "status": "Unknown", "code": 24,
     "manufacturer": "Generic", "device_id": r"USBPRINT\OLD", "present": False},
    {"name": "已停用的摄像头", "class": "Camera", "status": "Error", "code": 22,
     "manufacturer": "Sunplus", "device_id": r"USB\VID_1234&PID_5678", "present": True},
]

DRIVERS = [
    {"device_id": r"PCI\VEN_8086&DEV_2723&SUBSYS_00348086", "device_name": "Intel(R) Wireless-AC",
     "class": "NET", "version": "23.20.0.6", "date": "2026-01-15T00:00:00.0000000",
     "signer": "Microsoft Windows Hardware Compatibility Publisher", "inf": "netwtw06e.inf",
     "signed": True, "provider": "Intel"},
]


@pytest.fixture()
def faked(monkeypatch):
    monkeypatch.setattr(tools.devquery, "devices", lambda: [dict(item) for item in DEVICES])
    monkeypatch.setattr(tools.devquery, "drivers", lambda: [dict(item) for item in DRIVERS])


def _load(text: str) -> dict:
    return json.loads(text)


# --- problem-code words ------------------------------------------------------

def test_code_words_and_intentional_states():
    assert codes.code_of(28)["meaning"] == "no driver is installed for it"
    assert codes.code_of(22)["meaning"].startswith("disabled")
    assert codes.broken(28) and codes.broken(43)
    assert not codes.broken(0) and not codes.broken(22)  # a switched-off device is not broken
    assert codes.code_of(None) is None
    assert codes.code_of("junk") == {"code": "junk", "meaning": None}


# --- the listing -------------------------------------------------------------

def test_table_lists_present_only_and_flags_the_unhappy(faked):
    answer = _load(tools.win_device_table({}))
    names = [row["name"] for row in answer["devices"]]
    assert "旧打印机 (历史)" not in names  # absent by default
    assert any("LENOVO_VIRTUAL_BUS" in str(row["device_id"]) for row in answer["devices"])
    assert any("need attention" in note for note in answer["notes"])
    assert any("historical" in note for note in answer["notes"])


def test_table_broken_only_skips_the_disabled(faked):
    answer = _load(tools.win_device_table({"broken_only": True}))
    ids = [row["device_id"] for row in answer["devices"]]
    assert ids == [r"ROOT\LENOVO_VIRTUAL_BUS\0000"]  # code 28 yes, code 22 no


def test_table_filters_by_query_and_class_and_limit(faked):
    by_query = _load(tools.win_device_table({"query": "lenovo"}))
    assert len(by_query["devices"]) == 1
    by_class = _load(tools.win_device_table({"class": "net"}))
    assert [row["name"] for row in by_class["devices"]] == ["Intel(R) Wireless-AC"]
    limited = _load(tools.win_device_table({"limit": 1}))
    assert len(limited["devices"]) == 1
    assert any("stopped at limit" in note for note in limited["notes"])
    nothing = _load(tools.win_device_table({"query": "no-such-device"}))
    assert nothing["devices"] == [] and any("nothing matched" in n for n in nothing["notes"])


def test_table_include_absent_bring_history_back(faked):
    answer = _load(tools.win_device_table({"include_absent": True, "query": "旧打印机"}))
    assert len(answer["devices"]) == 1


# --- the detail --------------------------------------------------------------

def test_detail_matches_by_id_and_joins_the_driver(faked):
    answer = _load(tools.win_device_detail(
        {"name": r"PCI\VEN_8086&DEV_2723&SUBSYS_00348086"}))
    assert answer["ok"] is True
    assert answer["problem"]["meaning"] == "working"
    assert answer["driver"]["version"] == "23.20.0.6"
    assert answer["driver"]["date"] == "2026-01-15"
    assert answer["driver"]["signed"] is True


def test_detail_matches_by_name_substring(faked):
    answer = _load(tools.win_device_detail({"name": "无线"}))
    assert answer["ok"] is False  # the fake's Chinese name is 未知设备; try the other one
    answer = _load(tools.win_device_detail({"name": "Intel(R) Wireless"}))
    assert answer["ok"] is True and answer["class_name"] == "Net"


def test_detail_of_the_undriven_device_says_it_twice(faked):
    answer = _load(tools.win_device_detail({"name": "LENOVO"}))
    assert answer["problem"]["code"] == 28
    assert answer["driver"] is None
    assert any("no driver is installed" in note for note in answer["notes"])


def test_detail_of_a_disabled_device_is_not_an_alarm(faked):
    answer = _load(tools.win_device_detail({"name": "摄像头"}))
    assert answer["problem"]["code"] == 22
    assert any("on purpose" in note for note in answer["notes"])


def test_detail_suggests_when_nothing_matches(faked):
    answer = _load(tools.win_device_detail({"name": "nonexistent"}))
    assert answer["ok"] is False and answer["code"] == "not_found"
    no_name = _load(tools.win_device_detail({}))
    assert no_name["code"] == "name_required"


def test_detail_survives_a_dead_driver_table(monkeypatch):
    monkeypatch.setattr(tools.devquery, "devices", lambda: [dict(item) for item in DEVICES])
    def boom():
        raise tools.devquery.PowerShellError("no cim")
    monkeypatch.setattr(tools.devquery, "drivers", boom)
    answer = _load(tools.win_device_detail({"name": "Intel(R) Wireless"}))
    assert answer["ok"] is True
    assert answer["driver"] is None
    assert any("driver table could not be read" in n for n in answer["notes"])
