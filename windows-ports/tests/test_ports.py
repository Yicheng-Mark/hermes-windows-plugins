"""Tests: table parsing, filters, limits and the live listener round-trip."""

import json
import os
import socket
import sys

import pytest

from hermes_windows_ports import iphlp, tools

TCP_ROWS = [
    {"protocol": "tcp", "address": "0.0.0.0", "port": 3000, "remote_address": "0.0.0.0",
     "remote_port": 0, "state": "listen", "pid": 111},
    {"protocol": "tcp", "address": "127.0.0.1", "port": 8765, "remote_address": "127.0.0.1",
     "remote_port": 51234, "state": "established", "pid": 222},
    {"protocol": "tcp6", "address": "::1", "port": 3000, "remote_address": "::",
     "remote_port": 0, "state": "listen", "pid": 111},
]

UDP_ROWS = [
    {"protocol": "udp", "address": "0.0.0.0", "port": 5353, "remote_address": None,
     "remote_port": None, "state": "bound", "pid": 333},
]

NAMES = {
    111: "C:\\Program Files\\Hermes\\hermes.exe",
    222: "C:\\Program Files\\nodejs\\node.exe",
    333: "C:\\Windows\\System32\\svchost.exe",
}


@pytest.fixture
def fake_tables(monkeypatch):
    monkeypatch.setattr(iphlp, "tcp_rows", lambda include_ipv6=True: [
        row for row in TCP_ROWS if include_ipv6 or row["protocol"] == "tcp"
    ])
    monkeypatch.setattr(iphlp, "udp_rows", lambda include_ipv6=True: list(UDP_ROWS))
    iphlp._NAME_CACHE.clear()
    monkeypatch.setattr(iphlp, "process_name", lambda pid: NAMES.get(pid))
    return None


def load(text):
    payload = json.loads(text)
    assert payload["ok"] is True, payload
    return payload


def test_filter_by_port(fake_tables):
    payload = load(tools.win_port_owners({"port": 3000}))
    assert payload["matched"] == 2
    assert all(entry["port"] == 3000 for entry in payload["entries"])


def test_filter_by_port_list(fake_tables):
    payload = load(tools.win_port_owners({"ports": [3000, 5353]}))
    assert {entry["port"] for entry in payload["entries"]} == {3000, 5353}


def test_filter_by_state_listen(fake_tables):
    payload = load(tools.win_port_owners({"state": "listen"}))
    assert payload["matched"] == 2
    assert payload["listeners"] == 2
    assert all(entry["state"] == "listen" for entry in payload["entries"])


def test_filter_by_process_substring(fake_tables):
    payload = load(tools.win_port_owners({"process": "HERMES"}))
    assert payload["matched"] == 2
    assert {entry["process"] for entry in payload["entries"]} == {"hermes.exe"}


def test_protocol_filter_excludes_udp(fake_tables):
    payload = load(tools.win_port_owners({"protocol": "tcp"}))
    assert all(entry["protocol"].startswith("tcp") for entry in payload["entries"])
    udp_only = load(tools.win_port_owners({"protocol": "udp"}))
    assert [entry["port"] for entry in udp_only["entries"]] == [5353]


def test_ipv6_can_be_excluded(fake_tables):
    payload = load(tools.win_port_owners({"include_ipv6": False}))
    assert all(entry["protocol"] in ("tcp", "udp") for entry in payload["entries"])


def test_limit_and_summary(fake_tables):
    payload = load(tools.win_port_owners({"limit": 1}))
    assert len(payload["entries"]) == 1
    assert payload["by_process"]
    assert any("limit=1" in note for note in payload["notes"])


def test_no_match_explains_itself(fake_tables):
    payload = load(tools.win_port_owners({"port": 1}))
    assert payload["matched"] == 0
    assert any("no endpoint matched" in note for note in payload["notes"])


def test_bad_protocol_is_rejected(fake_tables):
    payload = json.loads(tools.win_port_owners({"protocol": "sctp"}))
    assert payload["ok"] is False


def test_table_error_is_returned_as_json(monkeypatch):
    def boom(include_ipv6=True):
        raise iphlp.WinNetError(5, "access denied")

    monkeypatch.setattr(iphlp, "tcp_rows", boom)
    payload = json.loads(tools.win_port_owners({"protocol": "tcp"}))
    assert payload["ok"] is False and payload["code"] == 5


def test_ipv4_and_port_decoding():
    assert iphlp._ipv4_text(0x0100007F) == "127.0.0.1"
    # Port 3000 arrives as the network-order bytes 0x0B 0xB8 in the low word.
    assert iphlp._port(0xB80B) == 3000
    assert iphlp._port(0x5000) == 80


def test_ipv6_text_formats_loopback():
    raw = [0] * 15 + [1]
    assert iphlp._ipv6_text(raw) == "::1"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_live_listener_round_trip():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        payload = json.loads(tools.win_port_owners({"port": port, "state": "listen"}))
        assert payload["ok"] is True
        entries = [entry for entry in payload["entries"] if entry["pid"] == os.getpid()]
        assert entries, payload
        assert entries[0]["port"] == port
        assert entries[0]["process"].lower().startswith("python")
    finally:
        server.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_live_full_table_is_consistent():
    payload = json.loads(tools.win_port_owners({"limit": 20}))
    assert payload["ok"] is True
    assert payload["matched"] == len(payload["entries"])
    assert payload["total_endpoints"] >= payload["matched"]
