"""The same two tools against this machine's real Task Scheduler (read-only)."""

from __future__ import annotations

import json
import sys

import pytest

from hermes_windows_tasks import taskpowershell, tools

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Task Scheduler is Windows only")


def test_the_cmdlets_answer_with_tasks() -> None:
    rows = taskpowershell.tasks()
    assert rows, "a Windows machine registers scheduled tasks"
    first = rows[0]
    assert str(first.get("path")).startswith("\\")
    assert first.get("state") in {"Ready", "Running", "Disabled", "Queued", "Unknown", "3", "4"}


def test_the_listing_reads_this_machines_tasks() -> None:
    result = json.loads(tools.win_scheduled_tasks({"limit": 20}))
    assert result["ok"] is True, result
    assert result["registered_total"] >= 1
    assert result["matched"] >= 1
    for row in result["entries"]:
        assert str(row["path"]).startswith("\\")
        assert row["last_result"] is None or "meaning" in row["last_result"]


def test_every_microsoft_task_can_be_filtered_out_and_asked_for() -> None:
    windows = json.loads(tools.win_scheduled_tasks({"include_microsoft": True, "limit": 500}))
    ours = json.loads(tools.win_scheduled_tasks({"limit": 500}))
    assert windows["matched"] >= ours["matched"]
    assert all(not str(row["path"]).lower().startswith("\\microsoft\\") for row in ours["entries"])


def test_a_listed_task_can_be_detailed() -> None:
    listing = json.loads(tools.win_scheduled_tasks({"limit": 3, "include_microsoft": True}))
    for row in listing["entries"]:
        detail = json.loads(tools.win_scheduled_task_detail({"name": row["path"]}))
        assert detail["ok"] is True, detail
        assert detail["path"].lower() == str(row["path"]).lower()
        assert detail["state"] == row["state"]
        # the export either parsed or said why not; both are answers, not exceptions
        assert isinstance(detail["triggers"], list)
