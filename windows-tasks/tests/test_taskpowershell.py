"""The cmdlet calls and their answers (hermes_windows_tasks/taskpowershell.py)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from hermes_windows_tasks import taskpowershell


class Finished:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_a_quote_is_doubled_and_nothing_else_is_escaped() -> None:
    assert taskpowershell.quote("plain") == "'plain'"
    assert taskpowershell.quote("it's") == "'it''s'"
    assert taskpowershell.quote(r"C:\a b\c") == r"'C:\a b\c'"


def test_a_task_path_splits_into_the_folder_and_the_name() -> None:
    assert taskpowershell.split_path("\\Hermes_Gateway") == ("\\", "Hermes_Gateway")
    assert taskpowershell.split_path("Hermes_Gateway") == ("\\", "Hermes_Gateway")
    assert taskpowershell.split_path("\\Microsoft\\Windows\\Defrag\\ScheduledDefrag") == (
        "\\Microsoft\\Windows\\Defrag\\",
        "ScheduledDefrag",
    )
    with pytest.raises(taskpowershell.PowerShellError):
        taskpowershell.split_path("\\")
    with pytest.raises(taskpowershell.PowerShellError):
        taskpowershell.split_path("\\A\\")


def test_one_task_comes_back_as_a_one_row_list(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = json.dumps({"path": "\\Only", "state": "Ready"}).encode()
    monkeypatch.setattr(taskpowershell.subprocess, "run", lambda *a, **k: Finished(answer))
    assert taskpowershell.tasks() == [{"path": "\\Only", "state": "Ready"}]


def test_a_byte_order_mark_does_not_hide_the_json(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = b"\xef\xbb\xbf" + json.dumps([{"path": "\\A"}]).encode()
    monkeypatch.setattr(taskpowershell.subprocess, "run", lambda *a, **k: Finished(answer))
    assert taskpowershell.tasks() == [{"path": "\\A"}]


def test_a_failed_powershell_is_an_error_with_its_complaint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_a: Any, **_k: Any) -> Finished:
        return Finished(stderr=b"Get-ScheduledTask : Access is denied", returncode=1)

    monkeypatch.setattr(taskpowershell.subprocess, "run", fail)
    with pytest.raises(taskpowershell.PowerShellError) as caught:
        taskpowershell.tasks()
    assert "Access is denied" in str(caught.value)


def test_silence_and_a_slow_answer_are_both_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(taskpowershell.subprocess, "run", lambda *a, **k: Finished())
    with pytest.raises(taskpowershell.PowerShellError):
        taskpowershell.tasks()

    def slow(*_a: Any, **_k: Any) -> Finished:
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=1)

    monkeypatch.setattr(taskpowershell.subprocess, "run", slow)
    with pytest.raises(taskpowershell.PowerShellError) as caught:
        taskpowershell.tasks()
    assert "did not answer" in str(caught.value)


def test_an_answer_that_is_not_json_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        taskpowershell.subprocess, "run", lambda *a, **k: Finished(b"WARNING: something")
    )
    with pytest.raises(taskpowershell.PowerShellError) as caught:
        taskpowershell.tasks()
    assert "not JSON" in str(caught.value)


def test_a_missing_powershell_is_reported_as_such(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*_a: Any, **_k: Any) -> Finished:
        raise FileNotFoundError("powershell.exe")

    monkeypatch.setattr(taskpowershell.subprocess, "run", missing)
    with pytest.raises(taskpowershell.PowerShellError) as caught:
        taskpowershell.tasks()
    assert "not on PATH" in str(caught.value)


def test_an_export_failure_comes_back_as_an_error_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = json.dumps({"error": "Access is denied"}).encode()
    monkeypatch.setattr(taskpowershell.subprocess, "run", lambda *a, **k: Finished(answer))
    assert taskpowershell.definition("\\A")["error"] == "Access is denied"
