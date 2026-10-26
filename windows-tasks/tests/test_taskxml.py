"""A definition file read as data (hermes_windows_tasks/taskxml.py)."""

from __future__ import annotations

import pytest

from hermes_windows_tasks import taskxml

DAILY = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>DOMAIN\\someone</Author>
    <Description>Keeps the thing going</Description>
    <URI>\\Maintenance\\Nightly</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T03:30:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-21-1</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>C:\\Tools\\nightly.cmd</Command>
      <Arguments>--quiet 2</Arguments>
      <WorkingDirectory>C:\\Tools</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def test_a_daily_task_parses_into_its_parts() -> None:
    # the files on disk are UTF-16 with a declaration that says so, and this is that
    parsed = taskxml.parse_definition(DAILY.encode("utf-16"))
    assert parsed["registration"]["author"] == "DOMAIN\\someone"
    assert parsed["registration"]["uri"] == "\\Maintenance\\Nightly"
    assert parsed["principal"]["run_level"] == "HighestAvailable"
    assert parsed["settings"]["enabled"] is True
    assert parsed["settings"]["disallow_start_if_on_batteries"] is True
    assert len(parsed["triggers"]) == 1
    assert parsed["triggers"][0]["kind"] == "CalendarTrigger"
    assert parsed["triggers"][0]["start_boundary"] == "2026-01-01T03:30:00"
    assert parsed["actions"][0]["command"] == "C:\\Tools\\nightly.cmd"
    assert taskxml.describe_action(parsed["actions"][0]) == "C:\\Tools\\nightly.cmd --quiet 2"


def test_a_disabled_hidden_task_says_so() -> None:
    disabled = DAILY.replace("<Enabled>true</Enabled>", "<Enabled>false</Enabled>").replace(
        "<Hidden>false</Hidden>", "<Hidden>true</Hidden>"
    )
    parsed = taskxml.parse_definition(disabled.encode("utf-16"))
    assert parsed["settings"]["enabled"] is False
    assert parsed["settings"]["hidden"] is True


def test_the_daily_trigger_reads_as_a_sentence() -> None:
    parsed = taskxml.parse_definition(DAILY.encode("utf-16"))
    assert taskxml.describe_trigger(parsed["triggers"][0]) == "every 1 day(s) at 03:30"


def test_a_weekly_trigger_names_its_days() -> None:
    weekly = DAILY.replace(
        "<ScheduleByDay>\n        <DaysInterval>1</DaysInterval>\n      </ScheduleByDay>",
        "<ScheduleByWeek><WeeksInterval>2</WeeksInterval>"
        "<DaysOfWeek><Monday /><Friday /></DaysOfWeek></ScheduleByWeek>",
    )
    parsed = taskxml.parse_definition(weekly.encode("utf-16"))
    assert taskxml.describe_trigger(parsed["triggers"][0]) == (
        "every 2 week(s) on Monday, Friday at 03:30"
    )


def test_a_monthly_trigger_names_its_days() -> None:
    monthly = DAILY.replace(
        "<ScheduleByDay>\n        <DaysInterval>1</DaysInterval>\n      </ScheduleByDay>",
        "<ScheduleByMonth><DaysOfMonth><Day>1</Day></DaysOfMonth></ScheduleByMonth>",
    )
    parsed = taskxml.parse_definition(monthly.encode("utf-16"))
    assert taskxml.describe_trigger(parsed["triggers"][0]) == (
        "every month on Day at 03:30"
    )


def test_boot_and_logon_triggers_are_each_read_in_their_own_words() -> None:
    boot = taskxml.parse_definition(
        b'<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        b"<Triggers><BootTrigger><Enabled>true</Enabled><Delay>PT1M</Delay></BootTrigger></Triggers>"
        b"</Task>"
    )
    assert boot["triggers"][0]["kind"] == "BootTrigger"
    assert taskxml.describe_trigger(boot["triggers"][0]) == "at startup after PT1M"

    logon = taskxml.parse_definition(
        b'<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        b"<Triggers><LogonTrigger><UserId>DOMAIN\\ada</UserId></LogonTrigger></Triggers></Task>"
    )
    assert taskxml.describe_trigger(logon["triggers"][0]) == "at logon of DOMAIN\\ada"


def test_a_repeating_trigger_says_how_often() -> None:
    repeating = taskxml.parse_definition(
        b'<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Triggers>'
        b"<TimeTrigger><StartBoundary>2026-01-01T09:00:00</StartBoundary>"
        b"<Repetition><Interval>PT1H</Interval><Duration>PT8H</Duration></Repetition>"
        b"</TimeTrigger></Triggers></Task>"
    )
    assert taskxml.describe_trigger(repeating["triggers"][0]) == (
        "once at 2026-01-01T09:00:00, repeating every PT1H for PT8H"
    )


def test_a_task_with_two_actions_keeps_both() -> None:
    two = DAILY.replace(
        "</Actions>",
        "<Exec><Command>C:\\Tools\\second.exe</Command></Exec></Actions>",
    )
    parsed = taskxml.parse_definition(two.encode("utf-16"))
    assert [action["command"] for action in parsed["actions"]] == [
        "C:\\Tools\\nightly.cmd",
        "C:\\Tools\\second.exe",
    ]


def test_a_definition_without_triggers_has_an_empty_list() -> None:
    parsed = taskxml.parse_definition(b"<Task><Settings><Enabled>false</Enabled></Settings></Task>")
    assert parsed["triggers"] == []
    assert parsed["actions"] == []
    assert parsed["settings"]["enabled"] is False
    # an element that is missing keeps the default the Scheduler itself assumes
    assert parsed["settings"]["hidden"] is False


def test_a_task_without_triggers_but_with_maintenance_settings_says_so() -> None:
    maintenance = taskxml.parse_definition(
        b'<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        b"<Triggers /><Settings><MaintenanceSettings><Period>P7D</Period>"
        b"<Deadline>P1M</Deadline></MaintenanceSettings></Settings></Task>"
    )
    assert maintenance["triggers"] == []
    assert maintenance["settings"]["maintenance"] == {"period": "P7D", "deadline": "P1M"}
    assert taskxml.parse_definition(b"<Task />")["settings"]["maintenance"] is None


def test_bytes_that_are_not_a_task_are_refused() -> None:
    with pytest.raises(taskxml.TaskXmlError):
        taskxml.parse_definition(b"<NotATask />")
    with pytest.raises(taskxml.TaskXmlError):
        taskxml.parse_definition(b"<Task><Triggers>")
    with pytest.raises(taskxml.TaskXmlError):
        taskxml.parse_definition(b"")


def test_the_exported_declaration_is_dropped_before_parsing() -> None:
    exported = DAILY  # Export-ScheduledTask hands back text that still declares UTF-16
    with pytest.raises(taskxml.TaskXmlError):
        taskxml.parse_definition(exported.encode("utf-8"))  # the declaration is a lie for UTF-8
    parsed = taskxml.parse_definition(taskxml.strip_declaration(exported).encode("utf-8"))
    assert parsed["registration"]["uri"] == "\\Maintenance\\Nightly"
    assert taskxml.strip_declaration("  <Task />") == "<Task />"
    assert taskxml.strip_declaration("\ufeff<?xml version='1.0'?><Task />") == "<Task />"


def test_a_clock_is_the_time_of_day_inside_a_boundary() -> None:
    assert taskxml.clock("2026-01-01T03:00:00") == "03:00"
    assert taskxml.clock("2026-01-01T03:30:15") == "03:30:15"
    assert taskxml.clock(None) is None
    assert taskxml.clock("2026-01-01") is None
