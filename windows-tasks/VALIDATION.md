# Validation

What was checked before this plugin was submitted, on which machine, and what the numbers
were. Everything below was run on Windows 11 (build 26300), Python 3.13, against
`hermes-agent` main at `749cb638` (2026-10-26).

## Admission checks

`validate_plugin_dir` from the current `main` tree (the function `hermes plugins validate`
runs) reports **15/15 checks pass, security scan safe, zero warnings** on this directory,
and again on the tree extracted from the repository tarball at the pinned commit. The plugin
suite is **40 passed** (36 unit, 4 live) on this machine and inside the pin tarball.

## Why the tools ask PowerShell instead of reading the store

Both places Windows keeps task definitions answered `access denied` to this unelevated
account:

```
winreg.OpenKey(HKLM, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree")
  -> [WinError 5] 拒绝访问 (access is denied)
os.listdir(r"C:\Windows\System32\Tasks")
  -> Permission denied
```

`Get-ScheduledTask` / `Export-ScheduledTask` answer the same account without elevation. That
is the whole reason for the PowerShell call; nothing is written, started or changed.

## What it reports, measured on this machine

- **195 tasks registered**, `win_scheduled_tasks({})` takes **1.43 s** (one PowerShell call
  that joins `Get-ScheduledTask` with `Get-ScheduledTaskInfo`).
- **14 tasks last ended with a failure**, and the codes are the useful part:
  `0x800710E0` on `\Microsoft\Windows\DiskCleanup\SilentCleanup` (it needs an interactive
  desktop and ran without one), `0x80040154` on
  `\Microsoft\Windows\AccountHealth\RecoverabilityToastTask` (the COM class is not
  registered), `0x40010004` on `\Microsoft\Windows\AppListBackup\BackupNonMaintenance`
  (terminated), `0x80070002` elsewhere.
- **A task with no triggers is not a broken task**: `Export-ScheduledTask` for
  `\Microsoft\Windows\Defrag\ScheduledDefrag` returns `<Triggers />` with
  `<MaintenanceSettings><Period>P7D</Period><Deadline>P1M</Deadline>`, and the detail says
  the task runs during automatic maintenance rather than printing an empty list.
- Trigger descriptions come from real definitions, not fixtures: `at logon of MARK\warri`
  (`\cua-driver-serve`), `once at 2026-10-04T08:51:46, repeating every PT1H`
  (`\WpsUpdateTask_warri`).
- `win_scheduled_task_detail` takes **1.7 s** (the listing call plus the export).

## Known limitations, measured

- **`schtasks /Query /FO CSV` disagrees with the cmdlets**: it printed **274 rows** against
  `Get-ScheduledTask`'s **195**, and its state column is localized (`����` here, on a Chinese
  Windows). The cmdlets are the source this plugin trusts.
- A task whose principal is another account can still be exported (the XPath, the actions and
  the triggers are there); what is missing is the *state*, which comes from the process the
  cmdlets talk to. When `Export-ScheduledTask` refuses, the detail still returns state,
  last result and next run from the listing, with a note naming the refusal.
- `LastTaskResult` arrives signed in JSON for codes above `0x7FFFFFFF`; the tool masks it to
  the unsigned 32-bit value the Scheduler means (`-2147024894` is shown as `0x80070002`).
- Two devices can be in the listing under one name only if Windows allows it; the path is
  the identity used everywhere here (`\Folder\Task`), which is what the cmdlets take.
