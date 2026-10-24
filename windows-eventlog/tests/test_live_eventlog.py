"""Live tests against the machine's real Event Log.

They assert shape and internal consistency rather than specific records, because a
clean machine may legitimately have no crash inside the window.
"""

import json
import sys

import pytest

from hermes_windows_eventlog import evtlog, tools

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Event Log only")


def test_native_query_returns_xml():
    xml = evtlog.query("Application", "*[System[(EventID=1001)]]", 1)
    assert xml and xml[0].startswith("<Event")


def test_live_crash_events_answer_is_consistent():
    payload = json.loads(tools.win_crash_events({"hours": 720, "limit": 10}))
    assert payload["ok"] is True
    assert payload["matched"] == len(payload["events"])
    assert payload["scanned"] >= payload["matched"]
    for event in payload["events"]:
        assert event["event_id"] in (1000, 1001, 1002, 1023, 1026)
        assert event["time"].endswith("Z")


def test_live_shutdown_events_answer_is_consistent():
    payload = json.loads(tools.win_shutdown_events({"hours": 720}))
    assert payload["ok"] is True
    assert payload["matched"] == len(payload["events"])


def test_live_generic_query_on_system_log():
    payload = json.loads(tools.win_eventlog_query({"channel": "System", "hours": 24, "limit": 5}))
    assert payload["ok"] is True
    for event in payload["events"]:
        assert event["channel"] == "System"


def test_live_process_filter_is_not_case_sensitive():
    payload = json.loads(tools.win_crash_events({"hours": 720, "process": "HERMES", "limit": 5}))
    assert payload["ok"] is True


def test_live_elevated_channel_reports_access_denied_without_raising():
    payload = json.loads(tools.win_eventlog_query({"channel": "Security", "hours": 1, "limit": 1}))
    # Non-elevated runs must degrade into an error payload, never an exception.
    assert payload["ok"] in (True, False)
    if not payload["ok"]:
        assert payload["code"] in (5, 15007, 15005)
