# Validation

What was actually run, on what, and what the numbers were. Everything below comes from a
real Windows machine reading its own event log, not from a mock of the OS API.

## Environment

- Windows 11 Home China (10.0.26300), x64.
- Python 3.13, `pytest 9.1.1`.
- Hermes source for the admission check: `main` at the commit this entry is validated
  against, fetched as the repository tarball and put on `PYTHONPATH` (the working copy and
  the pinned tarball are both checked; see below).

## Suites

| Command | Result |
|---|---|
| `python -m pytest tests -q` | 30 passed (24 unit + 6 live on Windows) |
| `python -m pytest tests -q` on a non-Windows interpreter | 24 passed, 6 skipped |

The unit suites run the handlers against a fake event source: XML shapes (named and
positional payloads, provider-schema records), time-window cutoffs, process/kind/level/id
filters, the scan cap, the record cap, and the access-denied path. The live suites query
the machine's real Application and System logs and assert internal consistency
(`matched == len(events)`, `scanned >= matched`, channel/id agreement) rather than specific
records, because a clean machine can legitimately have no crash in the window.

## Official validator

```
python -c "from hermes_cli.plugin_validate import validate_plugin_dir; ..."
```

Result on the working copy: **15 checks PASS, 0 warnings, security scan `safe`** —
manifest, fields, `requires_hermes` spec, config schema, `requires_env`, oauth, loadable,
python dependencies, capability probe, declared tools/hooks/middleware, built-in tool
collisions, security scan, no core override.

The same check is re-run against the **tarball of the pinned commit**, because the entry's
promise is about that tree, not about a working copy that may have uncommitted files.

## Observed on this machine

- `win_crash_events({"hours": 72})` scanned 54 Application records and matched 5, grouped
  into two signatures (`crashpad_log` x4, `RADAR_PRE_LEAK_64` x1).
- `win_shutdown_events({"hours": 720})` scanned 378 System records and returned the boot,
  shutdown, event-log start/stop and one operator-initiated restart, with the localized
  comment text preserved as-is.
- `win_eventlog_query({"channel": "Security"})` returned the structured access-denied error
  (`code: 5`) on a non-elevated account, with no exception.

## Disclosure

Read-only access to the event logs through `wevtapi` (`EvtQuery`, `EvtNext`, `EvtRender`,
`EvtClose`). No writes to any log, no log clearing, no channel configuration, no child
processes, no network calls, no files written. Tool output contains what the events contain:
application and module paths, exception codes, report ids and provider message text, which
can include user or machine paths.

The plugin does not read Windows Error Reporting report files. On a standard account those
directories can be listed but the report file inside them cannot be opened; the event-log
record of the same crash is readable and is what this plugin reads. Nothing here attempts to
obtain elevation.
