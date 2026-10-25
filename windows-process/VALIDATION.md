# Validation

What was checked before this plugin was submitted, on which machine, and what the numbers
were. Everything below was run on Windows 11 (build 26300), Python 3.13, against
`hermes-agent` main at `4dcef215` (2026-10-24).

## Admission checks

`validate_plugin_dir` from the current `main` tree — the same function `hermes plugins
validate` runs — reports **15/15 checks pass, security scan safe, zero warnings** on this
directory, and again on the tree extracted from the repository tarball at the pinned commit.

## Behaviour on the live process table

The table holds ~305 processes on an idle machine and building it (one `OpenProcess` +
`QueryFullProcessImageName` + `GetProcessTimes` per row) takes **11 ms**, so the tool does
not need a cache and the agent does not notice a wait.

The orphan detection was checked against the real table rather than a fixture:

| Process | Parent state | Why it is in the list |
|---|---|---|
| `cua-driver.exe` | gone | Started by a driver install 35 h ago from a shell that has since exited |
| `wps.exe` | gone | Office launcher whose parent exited |
| `cc-switch.exe` | gone | Tray app (started before this session) whose launcher exited |
| `tail.exe` | gone | A pipeline child whose shell exited seconds earlier |

And the ancestry walk, for the python process running the check:

```
python.exe <- bash.exe <- bash.exe <- bash.exe <- claude.exe <- Code.exe <- Code.exe <- explorer.exe
```

with `explorer.exe` reading `gone` (its own parent exited at logon), which is exactly the
shape the tool is meant to show.

## Known limitations, measured

- **152 of ~305 processes cannot be opened** (System, Idle, session managers, other accounts)
  and come back with no path and no start time. The summary counts them and the notes say so;
  the call still succeeds.
- **Session processes always read `gone`.** `csrss`, `wininit`, `winlogon`, `services` and
  `explorer` are started by a parent that exits by design. They are flagged `system: true`
  and the notes say how many of the flagged rows are theirs, so `include_system: false`
  leaves the four rows above and drops these five.
- **No `reused` row appeared on this machine** during the checks, which is expected: PID reuse
  needs a long-lived child plus enough process churn. The rule is unit-tested
  (`test_classify_parent_cases`) rather than taken on faith.

## Tests

`python -m pytest tests/` → **18 passed**: 14 unit tests over the classification rules,
filters, ordering and limits, plus 4 live tests that read the real table (they skip off
Windows). The live tests assert the process's own row, its parent chain, the age
monotonicity and the orphan filter, so a Windows API regression fails the suite rather than
silently returning empty rows.

## Security scan

`safe`, no findings. The plugin opens processes with `PROCESS_QUERY_LIMITED_INFORMATION`
only, never reads process memory, never duplicates or inherits a handle, writes nothing and
spawns nothing.
