"""The two tools over answers a test owns (hermes_windows_tasks/tools.py)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from hermes_windows_tasks import taskpowershell, tools

TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>ada</Author><URI>\\Alpha</URI></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-02-03T04:05:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger><UserId>ada</UserId></LogonTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>ada</UserId></Principal></Principals>
  <Settings><Enabled>true</Enabled><Hidden>false</Hidden></Settings>
  <Actions Context="Author"><Exec><Command>C:\\Tools\\alpha.exe</Command></Exec></Actions>
</Task>
"""

ROWS = [
    {
        "path": "\\Alpha",
        "state": "Ready",
        "user": "ada",
        "run_level": "Highest",
        "action": "C:\\Tools\\alpha.exe --quiet",
        "action_count": 1,
        "triggers": ["MSFT_TaskDailyTrigger", "MSFT_TaskLogonTrigger"],
        "last_run": "2026-10-26T04:05:00.0000000+08:00",
        "last_result": 0,
        "next_run": "2026-10-27T04:05:00.0000000+08:00",
        "missed_runs": 0,
    },
    {
        "path": "\\Broken",
        "state": "Ready",
        "user": "ada",
        "action": "",
        "action_count": 0,
        "triggers": ["MSFT_TaskTimeTrigger"],
        "last_run": None,
        "last_result": -2147024894,  # 0x80070002 as JSON writes it
        "next_run": None,
        "missed_runs": 3,
    },
    {
        "path": "\\Microsoft\\Windows\\Defrag\\ScheduledDefrag",
        "state": "Disabled",
        "group": "SYSTEM",
        "action": "C:\\Windows\\System32\\defrag.exe",
        "action_count": 1,
        "triggers": [],
        "last_run": None,
        "last_result": 267011,  # 0x41303, has not run yet
        "next_run": None,
        "missed_runs": 0,
    },
]


@pytest.fixture()
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(taskpowershell, "tasks", lambda **_k: ROWS)


def test_the_listing_leaves_out_windows_own_tasks_and_names_the_rest(live: None) -> None:
    result = json.loads(tools.win_scheduled_tasks({}))
    assert result["ok"] is True
    assert [row["path"] for row in result["entries"]] == ["\\Alpha", "\\Broken"]
    alpha = result["entries"][0]
    assert alpha["run_as"] == "ada"
    assert alpha["triggers"] == ["daily", "at logon"]
    assert alpha["last_result"]["meaning"] == "success"
    assert alpha["next_run"].startswith("2026-10-27")
    assert result["registered_total"] == 3
    assert result["failing_total"] == 1


def test_a_windows_written_result_code_is_read_as_the_same_number(live: None) -> None:
    result = json.loads(tools.win_scheduled_tasks({}))
    broken = {row["path"]: row for row in result["entries"]}["\\Broken"]
    assert broken["last_result"]["hex"] == "0x80070002"
    assert broken["last_result"]["meaning"] == "the program or script could not be found"


def test_failed_only_shows_what_last_ended_badly(live: None) -> None:
    result = json.loads(tools.win_scheduled_tasks({"failed_only": True}))
    assert [row["path"] for row in result["entries"]] == ["\\Broken"]
    assert any("last ended with a failure" in note for note in result["notes"])


def test_windows_own_tasks_come_back_when_asked_for(live: None) -> None:
    result = json.loads(tools.win_scheduled_tasks({"include_microsoft": True}))
    assert "\\Microsoft\\Windows\\Defrag\\ScheduledDefrag" in {
        row["path"] for row in result["entries"]
    }


def test_a_state_filter_is_applied_as_given(live: None) -> None:
    result = json.loads(
        tools.win_scheduled_tasks({"include_microsoft": True, "state": "disabled"})
    )
    assert [row["path"] for row in result["entries"]] == [
        "\\Microsoft\\Windows\\Defrag\\ScheduledDefrag"
    ]


def test_a_query_matches_the_task_path(live: None) -> None:
    result = json.loads(tools.win_scheduled_tasks({"query": "alph"}))
    assert [row["path"] for row in result["entries"]] == ["\\Alpha"]


def test_a_limit_stops_the_listing_and_says_so(live: None) -> None:
    result = json.loads(tools.win_scheduled_tasks({"limit": 1}))
    assert result["matched"] == 1
    assert any("stopped at limit" in note for note in result["notes"])


def test_a_long_action_is_clipped() -> None:
    long_action = "x" * (tools.ACTION_CHARS + 50)
    assert len(tools._clip(long_action)) == tools.ACTION_CHARS + 1
    assert tools._clip("a\n b") == "a b"


def test_a_result_the_table_does_not_know_is_still_reported() -> None:
    assert tools.result_of(0xDEADBEEF)["meaning"] == "no known meaning"
    assert tools.result_of(None) is None
    assert tools.result_of("not a number") == {"code": "not a number", "meaning": None}


def test_a_detail_carries_the_triggers_the_actions_and_the_run_facts(
    live: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(taskpowershell, "definition", lambda path, **_k: {"xml": TASK_XML})
    result = json.loads(tools.win_scheduled_task_detail({"name": "alpha"}))
    assert result["ok"] is True
    assert result["path"] == "\\Alpha"  # found without the leading backslash
    assert result["state"] == "Ready"
    assert result["last_result"]["meaning"] == "success"
    assert result["principal"]["user_id"] == "ada"
    assert [trigger["description"] for trigger in result["triggers"]] == [
        "every 1 day(s) at 04:05",
        "at logon of ada",
    ]
    assert result["actions"][0]["description"] == "C:\\Tools\\alpha.exe"
    assert result["notes"] == []


def test_a_definition_that_cannot_be_exported_still_answers(
    live: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        taskpowershell, "definition", lambda path, **_k: {"error": "Access is denied"}
    )
    result = json.loads(tools.win_scheduled_task_detail({"name": "\\Alpha"}))
    assert result["ok"] is True
    assert result["state"] == "Ready"  # what the listing knows is still there
    assert result["triggers"] == []
    assert any("Access is denied" in note for note in result["notes"])


def test_a_name_that_is_not_registered_says_what_is_close(live: None) -> None:
    result = json.loads(tools.win_scheduled_task_detail({"name": "\\Alp"}))
    assert result["ok"] is False
    assert result["code"] == "not_registered"
    assert result["suggestions"] == ["\\Alpha"]


def test_a_detail_without_a_name_is_refused(live: None) -> None:
    result = json.loads(tools.win_scheduled_task_detail({}))
    assert result["ok"] is False
    assert result["code"] == "name_required"


def test_powershell_that_does_not_answer_is_an_error_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**_kwargs: Any) -> list[dict[str, Any]]:
        raise taskpowershell.PowerShellError("PowerShell did not answer within 90s")

    monkeypatch.setattr(taskpowershell, "tasks", refuse)
    for answer in (tools.win_scheduled_tasks({}), tools.win_scheduled_task_detail({"name": "\\A"})):
        result = json.loads(answer)
        assert result["ok"] is False
        assert result["code"] == "tasks_unavailable"
