# hermes-windows-eventlog

Ask Windows **why the process died**, from inside Hermes.

Three read-only tools over the Windows Event Log:

| Tool | Answers |
|---|---|
| `win_crash_events` | Application Error / Application Hang / Windows Error Reporting / .NET Runtime records in a window, with the faulting module and a decoded exception code, plus groups that collapse repeated crashes of the same app and signature |
| `win_shutdown_events` | Kernel-Power 41 unexpected restarts, bugchecks decoded to names, EventLog 6008 dirty shutdowns, 1074 operator restarts with the process and comment, and the 6005/6006/12/13 start/stop markers |
| `win_eventlog_query` | Any channel with filters (event ids, levels, exact provider, substring) returning structured records instead of raw XML |

```python
win_crash_events({"hours": 24, "process": "hermes"})
win_crash_events({"hours": 168, "kinds": ["application_error"]})
win_shutdown_events({"hours": 720})
win_eventlog_query({"channel": "System", "event_ids": [7031, 7034], "contains": "gateway"})
```

## Why this exists

Hermes runs on Windows as a desktop app, a gateway and a pile of child processes. When one
of them disappears, the exit is silent: the session is gone, the log line never arrived,
and `hermes` came back with a new process and no explanation. Windows itself keeps the
record — the Application log has the faulting module, offset and exception code for every
crash and hang, and the System log has the machine-level story (unexpected restart,
bugcheck, operator shutdown) — but it is XML, it is spread over several providers, and the
interesting parts are codes like `0xC0000005` and `0x0000009F`.

This plugin turns that into three tool calls. The agent gets the same evidence a debugger
would start from, without shelling out to PowerShell and without a human reading event
viewer.

Two facts drove the design:

- **Crash evidence is not discoverable by file.** The Windows Error Reporting folders under
  `ProgramData` are ACL'd to the machine's administrators: on a normal user's machine the
  report directories can be listed but `Report.wer` inside them cannot be read. The event
  log record of the same crash *is* readable, and it carries the signature (app, version,
  bucket, event name). So the plugin reads the log, not the report files.
- **Not every `EventID 1000` is a crash.** Application-specific providers reuse the ids
  1000 and 1001 for informational events. Records are classified by provider as well as id;
  anything that is not the real crash family is dropped instead of being reported as a
  crash with empty fields.

## Requirements

- Windows 10 or 11.
- Hermes 0.21.4 or newer.
- Nothing else: stdlib only (`ctypes` + `xml.etree`), no Python dependencies, no child
  processes, no network calls.

## Install

```bash
git clone https://github.com/Yicheng-Mark/hermes-windows-eventlog \
  ~/.hermes/plugins/hermes-windows-eventlog
hermes plugins enable hermes-windows-eventlog
```

Or from the catalog: `hermes plugins install hermes-windows-eventlog`.

## What the output looks like

A real record from a machine that had a leak-detector event and a chain of crashpad
reports, `win_crash_events({"hours": 72})`:

```json
{
  "window_hours": 72.0,
  "matched": 5,
  "scanned": 54,
  "events": [
    {
      "kind": "wer",
      "time": "2026-10-20T03:00:08.013002Z",
      "app": "ego.exe",
      "app_version": "0.6.0.12",
      "event_name": "RADAR_PRE_LEAK_64",
      "bucket": "2219081324101382324",
      "report_id": "51a7d1d4-a23d-4599-93b5-ea257210ac15",
      "event_id": 1001,
      "provider": "Windows Error Reporting",
      "level": "information"
    }
  ],
  "groups": [
    {"app": "MicrosoftEdgeUpdate.exe", "signature": "crashpad_log", "count": 4,
     "first": "2026-10-19T14:11:34.004523Z", "last": "2026-10-20T00:15:30.905145Z",
     "modules": []}
  ],
  "notes": ["scanned 54 Application events in the last 72h"]
}
```

An Application Error record carries `module`, `module_path`, `offset` and a decoded
`exception` such as `0xC0000005 (ACCESS_VIOLATION)`; a Data Protection-style crash shows
`0xE0434352 (CLR_EXCEPTION)` for a managed throw. `win_shutdown_events` decodes bugcheck
codes (`159` from the provider or `0x0000009f` from WER both land on
`DRIVER_POWER_STATE_FAILURE`).

## Behaviour and limits

- Newest first. Queries stop as soon as the window start is crossed or the scan cap
  (5000 records) is hit, so a 30-day window over a busy log stays bounded.
- `limit` caps returned records at 200; long payload text is truncated and marked.
- Times are UTC, ISO 8601 with microseconds.
- Channel names are validated against a plain-name pattern, provider names must be exact
  and quote-free, and numeric filters are parsed as integers. Nothing from the model is
  interpolated into the query without those checks.
- Channels that need elevation (`Security` on a normal account) return
  `{"ok": false, "code": 5, "error": "..."}` instead of an exception.
- Provider data field names differ in casing between Windows builds (`Faulting Module
  Name` vs `Faulting module name`), so lookup is case-insensitive.
- Provider-supplied text is whatever the machine's locale produced (a reason string may be
  `重启`). The plugin does not translate or parse those strings.

## What this plugin does not do

- It is not a debugger and not a minidump reader. It reports what Windows recorded.
- It does not read Windows Error Reporting report files (they are not readable by a normal
  account) and does not elevate to get them.
- It does not write to a log, clear a log, configure a channel or start/stop a service.

## Disclosure

- **Read-only.** The plugin calls `EvtQuery` / `EvtNext` / `EvtRender` / `EvtClose` through
  `ctypes`. No writes, no log clearing, no channel configuration.
- **No child processes, no network, no files written.** The only file system work is the
  Python import system loading the plugin itself.
- **What reaches the model.** Whatever the queried events contain: application names and
  paths, faulting module paths, exception codes and offsets, report ids and buckets,
  service names, and provider-supplied message text. Event payloads routinely include user
  or machine paths (`C:\Users\<name>\...`). Treat tool output like any other local
  diagnostic output when sharing it.
- **Scope.** A process can read the logs its account is allowed to read. With a standard
  account that is Application, System and the per-user operational channels; elevation is
  required for `Security` and some system operational logs, and the plugin reports that as
  an error rather than trying to obtain it.
- **Windows only.** On other platforms the tools return a structured error.

## Tests

```bash
python -m pytest tests -q
```

30 tests: parsing, classification, filters, limits and error paths run against a fake event
source on every platform; the live suite exercises the real Application/System logs on
Windows (skipped elsewhere). See [VALIDATION.md](VALIDATION.md) for the run that was done
at this commit.

## License

MIT.
