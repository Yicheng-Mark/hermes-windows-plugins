# hermes-windows-services

Answer **"what runs as a service on this machine, why did one fail, and what does it depend
on"** on Windows, from inside Hermes.

```python
win_service_table({"nonzero_exit": True})
win_service_table({"state": "stopped", "start": "auto"})
win_service_detail({"name": "wuauserv"})
```

A Windows machine carries two to three hundred services, and when one of them is the reason
something does not work, the evidence is a number in a column nobody translates: the exit
code, the SCM event log behind it, and the failure policy nobody configured. These two tools
read all three and put them in words.

## What the tools report

| Field | Where it comes from |
|---|---|
| `state` | Running, Stopped, Paused (CIM `Win32_Service`) |
| `start` | Boot, System, Auto, Manual, Disabled, with the delayed flag folded in as `Auto, delayed` |
| `pid` | The process running it, or `null` when it is not |
| `exit_code` | The number, in hex, with what it means: `1077` has not tried since the last boot, `1053` did not answer in time, `1075` waits on a dependency that failed first, `2` a binary that is gone |
| `account`, `binary` | The logon account and command line from the registration |
| `depends_on`, `dependents` | The dependency edges both ways, `+`-prefixed load-order groups spelled out |

`win_service_detail` adds what a listing has no room for: what Windows does when the service
fails (restart it, restart the computer, run a command, after how many seconds, and when the
count resets — the `FailureActions` blob out of the registry, decoded), whether the
registered binary is still on disk, and the Service Control Manager's own record from the
System event log: `7000` failed to start, `7009` a start request that timed out, `7024` a
service-specific error, `7031` an unexpected end, `7045` an install. Routine noise (`7036`
state changes, `7040` start-type changes) is deliberately not collected.

## Read-only, and why it goes through PowerShell

Nothing is started, stopped, reconfigured or deleted: the tools query, and the schemas say
so.

The service listing comes from one `Get-CimInstance Win32_Service` call, whose property
names and enum values do not change with the display language — `sc.exe query` localizes
both. One child process (`powershell.exe`, hidden window, 90 s timeout) runs that call;
everything else — dependencies, the delayed flag, failure actions — is read straight from
`HKLM\SYSTEM\CurrentControlSet\Services` with `winreg`, no child process at all. The event
query is a second, per-detail PowerShell call that filters the System log by provider and
event id.

Two facts the hard way, both verified on Windows 11 (build 26300):

- **CIM's `DependOnService` property is never populated** — a listing of 293 services
  returned none, while the registry and `sc qc` both show them. Dependencies are read from
  the registry's `DependOnService` value (`MULTI_SZ`, a `+` prefix names a load-order
  group).
- **`FailureActions` is an undocumented binary value** with the 32-bit
  `SERVICE_FAILURE_ACTIONS` ABI: reset period, two string offsets, a count, an offset to
  the action array, then `type`/`delay` pairs. Decoded here directly; `wuauserv`'s blob
  reads back as three "restart after 60 s" actions, which is what the Services snap-in
  shows for it.

No network, no file writes, no elevation: everything these tools read is visible to a
normal user.

## Layout

```
plugin.yaml                        manifest: tools, tags, the read-only disclosure
hermes_windows_services/
  tools.py                         the two tools: filtering, rows, notes
  svcquery.py                      the CIM call and the event query (PowerShell)
  svcreg.py                        dependencies, delayed start, failure actions (winreg)
  exitcodes.py                     exit-code and SCM-event words
  schemas.py                       the tools' parameter schemas
tests/test_unit.py                 every layer with fakes; no PowerShell, no registry
tests/test_live.py                 the real CIM, registry and event log on this machine
```
