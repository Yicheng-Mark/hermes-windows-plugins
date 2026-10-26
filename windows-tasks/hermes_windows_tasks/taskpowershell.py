"""Every scheduled task, asked of the Task Scheduler's own cmdlets.

The store on disk is not readable without administrator rights: on Windows 11 both
``HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\TaskCache\\Tree`` and
``%SystemRoot%\\System32\\Tasks`` answer "access is denied" to a normal user, so a tool that
walked them would work only for an elevated agent. The ``ScheduledTasks`` cmdlets run
unelevated, and ``ConvertTo-Json`` gives an answer whose field names and values do not
change with the display language. ``schtasks /Query /FO CSV`` does change with it, and its
rows can be interrupted by error lines for tasks whose definitions are gone.

Two calls, both through ``powershell.exe``: one listing every task with its state and its
next and last run, and one per task that exports the definition as XML.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

POWERSHELL = "powershell.exe"
TIMEOUT = 90.0
# the agent talks to a person through an app window; a console must not flash over it
CREATE_NO_WINDOW = 0x08000000
# a pipe written by PowerShell may still start with a byte-order mark
_BOM = 0xFEFF

_HEADER = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;"

# Get-ScheduledTaskInfo is one call per task, so the info rows are collected once into a
# table keyed by path + name rather than asked for again inside the loop.
_LIST = """
$info = @{}
try {
  foreach ($row in (Get-ScheduledTask | Get-ScheduledTaskInfo)) {
    $info[$row.TaskPath + $row.TaskName] = $row
  }
} catch {
  # a task whose state cannot be read loses its last/next run, not the whole listing
}
$tasks = foreach ($task in Get-ScheduledTask) {
  $detail = $info[$task.TaskPath + $task.TaskName]
  [pscustomobject]@{
    path = $task.TaskPath + $task.TaskName
    state = [string]$task.State
    author = $task.Author
    user = $task.Principal.UserId
    group = $task.Principal.GroupId
    run_level = [string]$task.Principal.RunLevel
    action = (($task.Actions | ForEach-Object { ($_.Execute + ' ' + $_.Arguments).Trim() }) | Select-Object -First 1)
    action_count = @($task.Actions).Count
    triggers = @($task.Triggers | ForEach-Object { $_.CimClass.CimClassName })
    last_run = if ($detail -and $detail.LastRunTime) { $detail.LastRunTime.ToString('o') } else { $null }
    last_result = if ($detail) { $detail.LastTaskResult } else { $null }
    next_run = if ($detail -and $detail.NextRunTime) { $detail.NextRunTime.ToString('o') } else { $null }
    missed_runs = if ($detail) { $detail.NumberOfMissedRuns } else { $null }
  }
}
$tasks | ConvertTo-Json -Depth 5 -Compress
"""


class PowerShellError(Exception):
    """PowerShell is missing, slow, or answered something this module cannot use."""


def quote(text: str) -> str:
    """A PowerShell single-quoted string: ``'`` is written twice, nothing else is special."""
    return "'" + str(text).replace("'", "''") + "'"


def split_path(path: str) -> tuple[str, str]:
    """``\\A\\B\\Task`` as the two parameters the cmdlets want: ``\\A\\B\\`` and ``Task``."""
    cleaned = "\\" + str(path).strip().lstrip("\\")
    if cleaned == "\\":
        raise PowerShellError("a task path cannot be empty")
    folder, _, name = cleaned.rpartition("\\")
    if not name:
        raise PowerShellError(f"the path names no task: {path!r}")
    return folder + "\\", name


def run(script: str, timeout: float = TIMEOUT) -> Any:
    """PowerShell's JSON answer, parsed; every way it can fail comes back as PowerShellError."""
    argv = [
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    try:
        finished = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except FileNotFoundError as exc:
        raise PowerShellError(f"PowerShell is not on PATH: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PowerShellError(f"PowerShell did not answer within {timeout:.0f}s") from exc
    text = finished.stdout.decode("utf-8", errors="replace").lstrip(chr(_BOM)).strip()
    if finished.returncode != 0:
        complaint = finished.stderr.decode("utf-8", errors="replace").strip()
        raise PowerShellError(
            f"PowerShell exited {finished.returncode}: {(complaint or text)[:400]}"
        )
    if not text:
        raise PowerShellError("PowerShell answered nothing")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"PowerShell's answer was not JSON: {text[:200]}") from exc


def tasks(timeout: float = TIMEOUT) -> list[dict[str, Any]]:
    """Every scheduled task on this machine, with its state and its last and next run."""
    answer = run(_HEADER + _LIST, timeout)
    if isinstance(answer, dict):  # -Compress writes one object rather than a one-row array
        answer = [answer]
    if not isinstance(answer, list):
        raise PowerShellError(f"expected a list of tasks, got {type(answer).__name__}")
    return [row for row in answer if isinstance(row, dict)]


def definition(path: str, timeout: float = TIMEOUT) -> dict[str, Any]:
    """One task's definition, as ``{"xml": ...}`` or ``{"error": ...}``.

    ``Export-ScheduledTask`` is what Task Scheduler itself writes into the store, so this is
    the same document the definition file holds, without needing to read that file.
    """
    folder, name = split_path(path)
    script = _HEADER + (
        "try { @{ xml = (Export-ScheduledTask -TaskPath "
        f"{quote(folder)} -TaskName {quote(name)}) }} | ConvertTo-Json -Compress "
        "} catch { @{ error = $_.Exception.Message } | ConvertTo-Json -Compress }"
    )
    answer = run(script, timeout)
    if not isinstance(answer, dict):
        raise PowerShellError("expected an object with the definition")
    return answer


__all__ = ["PowerShellError", "definition", "quote", "run", "split_path", "tasks"]
