"""A Task Scheduler definition file, read as data.

Every scheduled task the Task Scheduler knows has a definition file under
``%SystemRoot%\\System32\\Tasks``: XML that names its triggers, its actions and the account it
runs as. Those files are written in a fixed schema, independent of the display language,
which is what makes them worth reading instead of parsing ``schtasks`` output; they do not
carry run state or last-run time, which live in the service and not on disk.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any


class TaskXmlError(Exception):
    """The bytes are not a task definition."""


_NAMESPACE = re.compile(r"^\{[^}]*\}")
_BOM = 0xFEFF  # the byte-order mark a string from PowerShell may carry


def _local(tag: str) -> str:
    return _NAMESPACE.sub("", tag)


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    for candidate in element:
        if _local(candidate.tag) == name:
            return candidate
    return None


def _text(element: ET.Element | None, name: str) -> str | None:
    found = _child(element, name)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _bool(element: ET.Element | None, name: str, default: bool | None = None) -> bool | None:
    value = _text(element, name)
    if value is None:
        return default
    return value.lower() in {"true", "1", "yes"}


def _flat(element: ET.Element) -> dict[str, Any]:
    """One level of child elements as a dict, nested ones included: a schedule, as it is."""
    out: dict[str, Any] = {}
    for candidate in element:
        name = _local(candidate.tag)
        if len(candidate):
            out[name] = _flat(candidate)
        else:
            out[name] = (candidate.text or "").strip() or None
    return out


def _trigger(element: ET.Element) -> dict[str, Any]:
    trigger: dict[str, Any] = {
        "kind": _local(element.tag),
        "enabled": _bool(element, "Enabled", True),
        "start_boundary": _text(element, "StartBoundary"),
        "end_boundary": _text(element, "EndBoundary"),
    }
    delay = _text(element, "Delay")
    if delay:
        trigger["delay"] = delay
    user = _text(element, "UserId")
    if user:
        trigger["user_id"] = user
    state_change = _text(element, "StateChange")
    if state_change:
        trigger["state_change"] = state_change
    repetition = _child(element, "Repetition")
    if repetition is not None:
        trigger["repetition"] = _flat(repetition)
    for name in (
        "ScheduleByDay",
        "ScheduleByWeek",
        "ScheduleByMonth",
        "ScheduleByMonthDayOfWeek",
    ):
        schedule = _child(element, name)
        if schedule is not None:
            # kept under its own name: a daily and a weekly trigger both have "schedule"
            trigger["schedule"] = {name: _flat(schedule)}
            break
    subscription = _text(element, "EventTrigger") or _text(element, "Subscription")
    if subscription:
        # an XPath expression over the event log: kept whole, it is the trigger's own words
        trigger["subscription"] = subscription
    return trigger


def _action(element: ET.Element) -> dict[str, Any]:
    action: dict[str, Any] = {"kind": _local(element.tag)}
    for name in ("Command", "Arguments", "WorkingDirectory", "ClassId", "Data"):
        value = _text(element, name)
        if value is not None:
            action[name.lower()] = value
    return action


def parse_definition(data: bytes) -> dict[str, Any]:
    """A definition file as ``{registration, principal, settings, triggers, actions}``.

    ``data`` is the bytes as found: the files are UTF-16 with a declaration that says so,
    and ElementTree honours it, so nothing here decodes the text itself.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise TaskXmlError(f"the definition is not valid XML: {exc}") from exc
    if _local(root.tag) != "Task":
        raise TaskXmlError(f"the definition's root is <{_local(root.tag)}>, not <Task>")

    registration = _child(root, "RegistrationInfo")
    principals = _child(root, "Principals")
    principal = None
    if principals is not None:
        for candidate in principals:
            principal = candidate
            break
    settings = _child(root, "Settings")
    maintenance = _child(settings, "MaintenanceSettings")
    triggers_parent = _child(root, "Triggers")
    actions_parent = _child(root, "Actions")

    return {
        "registration": {
            "author": _text(registration, "Author"),
            "description": _text(registration, "Description"),
            "uri": _text(registration, "URI"),
            "date": _text(registration, "Date"),
        },
        "principal": {
            "user_id": _text(principal, "UserId"),
            "group_id": _text(principal, "GroupId"),
            "logon_type": _text(principal, "LogonType"),
            "run_level": _text(principal, "RunLevel"),
        },
        "settings": {
            "enabled": _bool(settings, "Enabled", True),
            "hidden": _bool(settings, "Hidden", False),
            "disallow_start_if_on_batteries": _bool(settings, "DisallowStartIfOnBatteries"),
            "stop_if_going_on_batteries": _bool(settings, "StopIfGoingOnBatteries"),
            "start_when_available": _bool(settings, "StartWhenAvailable"),
            "multiple_instances": _text(settings, "MultipleInstancesPolicy"),
            "execution_time_limit": _text(settings, "ExecutionTimeLimit"),
            # a task with no triggers and this element runs during automatic maintenance
            "maintenance": (
                {"period": _text(maintenance, "Period"), "deadline": _text(maintenance, "Deadline")}
                if maintenance is not None
                else None
            ),
        },
        "triggers": [_trigger(child) for child in (triggers_parent if triggers_parent is not None else [])],
        "actions": [_action(child) for child in (actions_parent if actions_parent is not None else [])],
    }


def strip_declaration(text: str) -> str:
    """The XML declaration, dropped.

    ``Export-ScheduledTask`` hands the document back as text that still declares UTF-16
    while the text itself is a Python string: ElementTree refuses that combination, and the
    declaration carries nothing else this module needs.
    """
    stripped = text.lstrip(chr(_BOM) + ' \t\r\n')
    if not stripped.startswith("<?xml"):
        return stripped
    end = stripped.find("?>")
    return stripped[end + 2 :].lstrip() if end != -1 else stripped


def clock(start_boundary: str | None) -> str | None:
    """The time of day inside a start boundary: ``...T03:00:00`` reads ``03:00``."""
    if not start_boundary or "T" not in start_boundary:
        return None
    time = start_boundary.split("T", 1)[1]
    if time.endswith(":00") and time.count(":") == 2:
        time = time[:-3]
    return time or None


def describe_trigger(trigger: dict[str, Any]) -> str:
    """One trigger in a sentence, for a listing that has no room for the whole schema."""
    kind = trigger.get("kind") or "Trigger"
    enabled = "" if trigger.get("enabled", True) else ", disabled"
    at = clock(trigger.get("start_boundary"))
    schedule = trigger.get("schedule") or {}
    if kind == "BootTrigger":
        text = "at startup"
        if trigger.get("delay"):
            text += f" after {trigger['delay']}"
    elif kind == "LogonTrigger":
        text = "at logon" + (f" of {trigger['user_id']}" if trigger.get("user_id") else "")
    elif kind == "SessionStateChangeTrigger":
        text = f"on session {trigger.get('state_change') or 'state change'}"
    elif kind == "EventTrigger":
        text = "on event"
    elif schedule.get("ScheduleByDay"):
        days = (schedule["ScheduleByDay"] or {}).get("DaysInterval") or "1"
        text = f"every {days} day(s)" + (f" at {at}" if at else "")
    elif schedule.get("ScheduleByWeek"):
        week = schedule["ScheduleByWeek"] or {}
        days_of_week = week.get("DaysOfWeek") or {}
        names = ", ".join(str(name) for name in days_of_week) or "no day named"
        weeks = week.get("WeeksInterval") or "1"
        text = f"every {weeks} week(s) on {names}" + (f" at {at}" if at else "")
    elif schedule.get("ScheduleByMonth"):
        month = schedule["ScheduleByMonth"] or {}
        days = month.get("DaysOfMonth") or {}
        names = ", ".join(str(name) for name in days) or "no day named"
        months = month.get("Months") or {}
        which = ", ".join(str(name) for name in months) if months else "every month"
        text = f"{which} on {names}" + (f" at {at}" if at else "")
    elif kind == "TimeTrigger":
        text = f"once at {trigger.get('start_boundary') or 'once'}"
    else:
        text = f"{kind}" + (f" at {at}" if at else "")
    repetition = trigger.get("repetition") or {}
    if repetition.get("Interval"):
        text += f", repeating every {repetition['Interval']}"
        if repetition.get("Duration"):
            text += f" for {repetition['Duration']}"
    return text + enabled


def describe_action(action: dict[str, Any]) -> str:
    """One action as the command line a person would run."""
    if action.get("kind") == "Exec":
        command = action.get("command") or ""
        arguments = action.get("arguments")
        return f"{command} {arguments}".strip() if arguments else command
    details = action.get("classid") or action.get("data") or ""
    return f"{action.get('kind')} {details}".strip()


__all__ = [
    "TaskXmlError",
    "clock",
    "describe_action",
    "describe_trigger",
    "parse_definition",
    "strip_declaration",
]
