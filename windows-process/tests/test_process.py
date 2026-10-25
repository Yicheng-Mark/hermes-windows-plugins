"""Tests: parent classification, filters, limits and the live process round-trip."""

import json
import os
import sys
import time

import pytest

from hermes_windows_process import proctab, tools

# (pid, parent_pid, name, started)
ROWS = [
    (1, 0, "init.exe", 100.0),
    (100, 1, "parent.exe", 1000.0),
    (101, 100, "child.exe", 2000.0),
    (102, 999, "orphan.exe", 3000.0),
    (103, 100, "reused.exe", 500.0),
    (104, 0, "root.exe", None),
]

PATHS = {
    1: "C:\\Fake\\init.exe",
    100: "C:\\Program Files\\Fake\\parent.exe",
    101: "C:\\Program Files\\Fake\\child.exe",
    102: "C:\\Temp\\orphan.exe",
    103: "C:\\Program Files\\Fake\\reused.exe",
}


@pytest.fixture
def fake_table(monkeypatch):
    monkeypatch.setattr(proctab, "snapshot", lambda: [
        {"pid": pid, "parent_pid": ppid, "name": name, "threads": 2}
        for pid, ppid, name, _ in ROWS
    ])
    starts = {pid: started for pid, _, _, started in ROWS}
    monkeypatch.setattr(proctab, "details", lambda pid: (PATHS.get(pid), starts.get(pid)))
    return None


def load(text):
    payload = json.loads(text)
    assert payload["ok"] is True, payload
    return payload


def test_classify_parent_cases():
    assert tools.classify_parent(2000.0, 0, None, False) == tools.PARENT_ROOT
    assert tools.classify_parent(2000.0, 999, None, False) == tools.PARENT_GONE
    assert tools.classify_parent(2000.0, 100, 1000.0, True) == tools.PARENT_ALIVE
    assert tools.classify_parent(500.0, 100, 1000.0, True) == tools.PARENT_REUSED
    assert tools.classify_parent(None, 100, 1000.0, True) == tools.PARENT_UNKNOWN
    assert tools.classify_parent(2000.0, 100, None, True) == tools.PARENT_UNKNOWN


def test_orphans_only_returns_gone_and_reused(fake_table):
    payload = load(tools.win_process_table({"orphans_only": True}))
    states = {entry["pid"]: entry["parent_state"] for entry in payload["entries"]}
    assert states == {102: "gone", 103: "reused"}
    assert payload["orphans"] == 2


def test_parent_state_is_attached_to_every_row(fake_table):
    payload = load(tools.win_process_table({}))
    states = {entry["pid"]: entry["parent_state"] for entry in payload["entries"]}
    assert states[100] == "alive"
    assert states[101] == "alive"
    assert states[104] == "root"


def test_filter_by_process_name(fake_table):
    payload = load(tools.win_process_table({"process": "orph"}))
    assert [entry["pid"] for entry in payload["entries"]] == [102]


def test_filter_by_path(fake_table):
    payload = load(tools.win_process_table({"process": "c:\\temp"}))
    assert [entry["pid"] for entry in payload["entries"]] == [102]


def test_filter_by_parent(fake_table):
    payload = load(tools.win_process_table({"parent": 100}))
    assert {entry["pid"] for entry in payload["entries"]} == {101, 103}


def test_filter_by_pid_list(fake_table):
    payload = load(tools.win_process_table({"pids": [101, 104]}))
    assert {entry["pid"] for entry in payload["entries"]} == {101, 104}


def test_ancestry_is_returned_as_context(fake_table):
    payload = load(tools.win_process_table({"pid": 101, "with_ancestry": True}))
    assert [entry["pid"] for entry in payload["entries"]] == [101]
    context = {entry["pid"]: entry for entry in payload["ancestry"]}
    assert 100 in context
    assert context[100]["context"] is True


def test_include_system_false_drops_unreadable(fake_table):
    payload = load(tools.win_process_table({"include_system": False}))
    assert 104 not in {entry["pid"] for entry in payload["entries"]}


def test_system_flag_marks_windows_tree_images(monkeypatch):
    monkeypatch.setattr(proctab, "snapshot", lambda: [
        {"pid": 10, "parent_pid": 0, "name": "csrss.exe", "threads": 10},
        {"pid": 11, "parent_pid": 0, "name": "python.exe", "threads": 3},
    ])
    monkeypatch.setattr(
        proctab,
        "details",
        lambda pid: ("C:\\Windows\\System32\\csrss.exe", 900.0) if pid == 10 else ("D:\\Python\\python.exe", 950.0),
    )
    payload = load(tools.win_process_table({}))
    flags = {entry["pid"]: entry["system"] for entry in payload["entries"]}
    assert flags == {10: True, 11: False}
    filtered = load(tools.win_process_table({"include_system": False}))
    assert [entry["pid"] for entry in filtered["entries"]] == [11]


def test_limit_is_respected(fake_table):
    payload = load(tools.win_process_table({"limit": 2}))
    assert payload["matched"] == 2
    assert len(payload["entries"]) == 2


def test_oldest_first_ordering(fake_table):
    payload = load(tools.win_process_table({}))
    ages = [entry["age_seconds"] for entry in payload["entries"] if entry["age_seconds"]]
    assert ages == sorted(ages, reverse=True)


def test_filetime_conversion():
    # 2026-01-01T00:00:00Z in FILETIME ticks
    ticks = (1_767_225_600 + proctab.FILETIME_EPOCH_OFFSET) * 10_000_000
    assert proctab.filetime_to_epoch(ticks) == 1_767_225_600


def test_error_is_reported_not_raised(monkeypatch):
    def boom():
        raise proctab.WinProcError("snapshot failed", 6)

    monkeypatch.setattr(proctab, "snapshot", boom)
    payload = json.loads(tools.win_process_table({}))
    assert payload["ok"] is False
    assert payload["code"] == 6


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_live_self_row():
    payload = load(tools.win_process_table({"pid": os.getpid()}))
    entry = payload["entries"][0]
    assert entry["pid"] == os.getpid()
    assert entry["parent_pid"] == os.getppid()
    assert entry["process"].lower().startswith("python")
    assert entry["path"]
    assert entry["age_seconds"] is not None and entry["age_seconds"] >= 0
    assert entry["started"].endswith("Z")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_live_live_parent_chain_reaches_ancestry():
    payload = load(tools.win_process_table({"pid": os.getpid(), "with_ancestry": True}))
    pids = {entry["pid"] for entry in payload["ancestry"]}
    assert os.getppid() in pids


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_live_table_is_consistent():
    payload = load(tools.win_process_table({"limit": 25}))
    assert payload["matched"] == len(payload["entries"])
    assert payload["total_processes"] > 10
    assert payload["orphans"] >= 0
    for entry in payload["entries"]:
        assert entry["parent_state"] in {
            "alive", "gone", "reused", "unknown", "root",
        }


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_live_orphan_scan_does_not_blow_up():
    payload = load(tools.win_process_table({"orphans_only": True, "limit": 5}))
    for entry in payload["entries"]:
        assert entry["parent_state"] in ("gone", "reused")
