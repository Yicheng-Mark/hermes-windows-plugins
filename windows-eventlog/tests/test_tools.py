"""Tool-handler tests over a fake Event Log (no Win32 calls)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from hermes_windows_eventlog import evtlog, tools


def event_xml(
    event_id,
    provider="Application Error",
    level=2,
    minutes_ago=10,
    data=None,
    channel="Application",
):
    when = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "0Z"
    fields = "".join(
        f"<Data Name='{name}'>{value}</Data>" for name, value in (data or {}).items()
    )
    return (
        "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
        f"<Provider Name='{provider}'/><EventID>{event_id}</EventID><Level>{level}</Level>"
        f"<TimeCreated SystemTime='{stamp}'/>"
        f"<Execution ProcessID='4242' ThreadID='1'/><Channel>{channel}</Channel></System>"
        f"<EventData>{fields}</EventData></Event>"
    )


CRASH = {
    "Application Name": "hermes.exe",
    "Application Version": "0.22.2",
    "Faulting module name": "kernelbase.dll",
    "Exception code": "0xc0000005",
    "Fault Offset": "0x1234",
}


@pytest.fixture
def fake_log(monkeypatch):
    state = {"xml": [], "calls": []}

    def fake_iter(channel, xpath, limit):
        state["calls"].append((channel, xpath, limit))
        yield from state["xml"][:limit]

    monkeypatch.setattr(evtlog, "iter_events", fake_iter)
    return state


def load(text):
    payload = json.loads(text)
    assert payload["ok"] is True, payload
    return payload


def test_crash_events_return_records_and_groups(fake_log):
    fake_log["xml"] = [
        event_xml(1000, data=CRASH, minutes_ago=5),
        event_xml(1000, data=CRASH, minutes_ago=30),
        event_xml(1001, provider="Windows Error Reporting", level=4, minutes_ago=60,
                  data={"P1": "ego.exe", "EventName": "APPCRASH"}),
    ]
    payload = load(tools.win_crash_events({"hours": 24}))
    assert payload["matched"] == 3
    kinds = [event["kind"] for event in payload["events"]]
    assert kinds == ["application_error", "application_error", "wer"]
    assert payload["events"][0]["exception"] == "0xC0000005 (ACCESS_VIOLATION)"
    assert payload["events"][0]["module"] == "kernelbase.dll"
    assert payload["groups"][0]["count"] == 2
    assert payload["groups"][0]["app"] == "hermes.exe"
    assert payload["groups"][0]["signature"].startswith("0xC0000005")


def test_crash_events_filter_by_process(fake_log):
    fake_log["xml"] = [
        event_xml(1000, data=CRASH),
        event_xml(1000, data={**CRASH, "Application Name": "codex.exe"}),
    ]
    payload = load(tools.win_crash_events({"process": "CODEX"}))
    assert payload["matched"] == 1
    assert payload["events"][0]["app"] == "codex.exe"


def test_crash_events_filter_by_kind(fake_log):
    fake_log["xml"] = [
        event_xml(1000, data=CRASH),
        event_xml(1002, provider='Application Hang', data=CRASH),
    ]
    payload = load(tools.win_crash_events({"kinds": ["application_hang"]}))
    assert [event["kind"] for event in payload["events"]] == ["application_hang"]


def test_crash_events_stop_at_the_window_start(fake_log):
    fake_log["xml"] = [
        event_xml(1000, data=CRASH, minutes_ago=10),
        event_xml(1000, data=CRASH, minutes_ago=60 * 48),
        event_xml(1000, data=CRASH, minutes_ago=20),
    ]
    payload = load(tools.win_crash_events({"hours": 24}))
    assert payload["matched"] == 1
    assert payload["scanned"] == 2


def test_crash_events_respects_limit(fake_log):
    fake_log["xml"] = [event_xml(1000, data=CRASH, minutes_ago=index) for index in range(1, 11)]
    payload = load(tools.win_crash_events({"limit": 3}))
    assert len(payload["events"]) == 3


def test_crash_events_explains_an_empty_result(fake_log):
    payload = load(tools.win_crash_events({}))
    assert payload["matched"] == 0
    assert any("no crash records" in note for note in payload["notes"])


def test_dotnet_events_keep_exception_text(fake_log):
    fake_log["xml"] = [
        event_xml(1026, provider=".NET Runtime", data={
            "Application": "hermes.exe",
            "Exception Info": "System.InvalidOperationException: boom",
        })
    ]
    payload = load(tools.win_crash_events({}))
    assert payload["events"][0]["kind"] == "dotnet"
    assert "InvalidOperationException" in payload["events"][0]["exception_text"]


def test_shutdown_events_classify_power_loss_and_bugcheck(fake_log):
    fake_log["xml"] = [
        event_xml(41, provider="Microsoft-Windows-Kernel-Power", level=1, minutes_ago=5,
                  data={"BugcheckCode": "159", "PowerButtonTimestamp": "0"}, channel="System"),
        event_xml(6008, provider="EventLog", level=2, minutes_ago=6,
                  data={"param1": "8:00:00", "param2": "2026-10-20"}, channel="System"),
        event_xml(1001, provider="Microsoft-Windows-WER-SystemErrorReporting", level=2,
                  minutes_ago=7, data={"BugcheckCode": "0x0000009f"}, channel="System"),
    ]
    payload = load(tools.win_shutdown_events({"hours": 24}))
    kinds = [event["kind"] for event in payload["events"]]
    assert kinds == ["unexpected_restart", "unexpected_shutdown", "bugcheck"]
    assert payload["events"][0]["bugcheck"] == "DRIVER_POWER_STATE_FAILURE"
    assert payload["events"][2]["bugcheck"] == "DRIVER_POWER_STATE_FAILURE"


def test_shutdown_events_keep_operator_restart_details(fake_log):
    fake_log["xml"] = [
        event_xml(1074, provider="User32", level=4, minutes_ago=3, channel="System",
                  data={"param1": "C:\\Windows\\system32\\svchost.exe",
                        "param2": "0x80010000",
                        "param5": "Windows Update"}),
    ]
    payload = load(tools.win_shutdown_events({}))
    event = payload["events"][0]
    assert event["kind"] == "initiated_shutdown"
    assert event["process"].endswith("svchost.exe")
    assert event["comment"] == "Windows Update"


def test_generic_query_filters_and_details(fake_log):
    fake_log["xml"] = [
        event_xml(7031, provider="Service Control Manager", level=2, minutes_ago=1,
                  channel="System", data={"param1": "HermesGateway"}),
        event_xml(7036, provider="Service Control Manager", level=4, minutes_ago=2,
                  channel="System", data={"param1": "Spooler"}),
    ]
    payload = load(tools.win_eventlog_query({
        "channel": "System", "event_ids": [7031], "include_details": True,
    }))
    assert payload["matched"] == 1
    assert payload["events"][0]["event_id"] == 7031
    assert payload["events"][0]["data"]["param1"] == "HermesGateway"


def test_generic_query_contains_filter(fake_log):
    fake_log["xml"] = [
        event_xml(7031, provider="Service Control Manager", minutes_ago=1,
                  channel="System", data={"param1": "HermesGateway"}),
    ]
    assert load(tools.win_eventlog_query({"contains": "hermesgateway"}))["matched"] == 1
    assert load(tools.win_eventlog_query({"contains": "nothing"}),)["matched"] == 0


def test_generic_query_rejects_bad_channel_and_provider(fake_log):
    bad_channel = json.loads(tools.win_eventlog_query({"channel": "Application']"}))
    assert bad_channel["ok"] is False
    bad_provider = json.loads(tools.win_eventlog_query({"provider": "a'b"}))
    assert bad_provider["ok"] is False
    assert fake_log["calls"] == []


def test_event_log_error_is_returned_as_json(monkeypatch):
    def boom(channel, xpath, limit):
        raise evtlog.EventLogError(5, "access denied (this channel needs elevation)")
        yield  # pragma: no cover

    monkeypatch.setattr(evtlog, "iter_events", boom)
    payload = json.loads(tools.win_eventlog_query({"channel": "Security"}))
    assert payload["ok"] is False
    assert payload["code"] == 5
    assert "access denied" in payload["error"]


def test_handlers_accept_context_kwargs(fake_log):
    fake_log["xml"] = [event_xml(1000, data=CRASH)]
    payload = load(tools.win_crash_events({}, task_id="t-1", session_id="s-1"))
    assert payload["matched"] == 1
