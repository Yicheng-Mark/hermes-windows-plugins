# hermes-windows-tasks

Answer **"what does this machine run on its own, and did it work"** on Windows, from inside
Hermes.

```python
win_scheduled_tasks({"query": "wps"})
win_scheduled_tasks({"failed_only": True, "include_microsoft": True})
win_scheduled_tasks({"state": "disabled"})
win_scheduled_task_detail({"name": "\\Microsoft\\Windows\\Defrag\\ScheduledDefrag"})
```

Windows starts a great deal of what it does, and what installed software wants it to do,
through Task Scheduler: at logon, at boot, every hour, or during automatic maintenance. When
one of those starts failing, the only place that says so is the "Last Run Result" column of
Task Scheduler, as a number. These two tools read that column and translate it.

## What the tools report

| Field | Where it comes from |
|---|---|
| `state` | Ready, Running, Disabled, Queued |
| `run_as`, `run_level` | The task's principal (a user, a SID such as `S-1-5-18`, or a group) |
| `action` | The first action's command line |
| `triggers` | The trigger classes in words: at logon, daily, weekly, at a time, on event |
| `last_run`, `next_run` | ISO 8601 timestamps with the machine's offset |
| `last_result` | The code, in hex, with what it means: `0x80070002` is a program that is no longer there, `0x800710E0` a task that needs a desktop it did not have, `0x40010004` one that was stopped |
| `missed_runs` | Runs the scheduler skipped, typically because the machine was off |

`win_scheduled_task_detail` adds what a listing has no room for: every trigger with its start
boundary, repetition and schedule, every action with arguments and working directory, the
principal, and the settings that decide whether a task runs on battery or when late. A task
with no triggers and `MaintenanceSettings` runs during automatic maintenance, and the notes
say so instead of leaving an empty list to be misread.

## Read-only, and why it goes through PowerShell

Nothing is created, started, changed or deleted: the tools query, and the schemas say so.

The task *store* on disk is not readable without administrator rights. On Windows 11 (build
26300) both `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree` and
`%SystemRoot%\System32\Tasks` answer `[WinError 5] Access is denied` to a normal user, so a
tool that walked them would work only for an elevated agent. The `ScheduledTasks` cmdlets run
unelevated, and `ConvertTo-Json` gives field names and values that do not change with the
display language.

`schtasks /Query /FO CSV` is the usual alternative and it is the wrong one: its header and
state words are localized, and for a registration whose definition file is gone it prints an
`ERROR: Task cannot be loaded` line in the middle of the rows, which is what makes naive
readers of it fail (hermes-agent issue #142140 is exactly that failure in `hermes gateway
ensure`). These tools ask the cmdlets instead.

## Cost

One PowerShell call for the listing (about **1.4 s** for 195 tasks on this machine) and a
second one only when a single definition is asked for. There is no cache: scheduled tasks
change when software is installed, and a stale answer here is worse than a slow one.

## Platform

Windows only. There are no Python dependencies, no network calls and no file writes.
