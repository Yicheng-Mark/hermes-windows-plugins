# hermes-windows-startup

Answer **"what launches itself on this machine"** on Windows, from inside Hermes.

```python
win_startup_table({"include_disabled": False})
win_startup_table({"scope": "machine"})
win_startup_detail({"name": "CC Switch"})
```

The Task Manager → Startup tab question, answered without Task Manager: what runs at
sign-in, from which of the six Run/RunOnce keys or the two Startup folders, and — the
part `Win32_StartupCommand` has no field for — whether the person switched it off, with
the date of that decision.

## What the tools report

| Field | Where it comes from |
|---|---|
| `name`, `command` | The Run value's name and data, or the folder file, verbatim |
| `source` | One of six registry keys (`registry-hkcu-run`, `registry-hklm-run-32`, ...) or `folder-user` / `folder-common` |
| `scope` | `user` or `machine` |
| `enabled`, `changed` | Explorer's `StartupApproved` verdict: enabled (`02`/`03`), disabled in Task Manager (`06`/`07`), with the FILETIME of the last change; an entry with no record runs — that is Windows' default |
| leftover approvals | Records for entries that are gone — uninstalled programs leave them behind; reported, not guessed from |

`win_startup_detail` adds the resolution of the command: quoting, arguments and
environment variables folded in, the binary the loader would find, and whether it is
still on disk — an uninstalled launcher's Run entry keeps pointing at nothing. Unquoted
commands with spaces in the path (real machines write them) are resolved the way the
loader resolves them: the longest whitespace prefix that names a real file.

## Read-only, and why it goes through the registry

Nothing is enabled, disabled or deleted: the tools enumerate, and the schemas say so.

The registry and the two folders answer in about a millisecond on this machine — three
Run entries and two folders — with no PowerShell spawn and no WMI query. `Win32_StartupCommand`
costs both and cannot answer the switched-off question at all, because Explorer keeps
that verdict in `StartupApproved` blobs the CIM class never reads.

The `StartupApproved` record is 12 bytes: a state word whose low byte Explorer writes
(`02`/`03` enabled, `06`/`07` switched off) and a FILETIME of when it was last changed.
Other bytes occur in the wild — a record an uninstalled program orphaned reads `01` here —
and are reported as unknown with the raw byte, never guessed into a verdict.

Startup folders are read through Explorer's own `User Shell Folders` values, so a
OneDrive-redirected Startup folder is found where the person actually has it, not where
the default says it should be. `desktop.ini` is folder customization, not something
anyone launches, and is skipped.

## Windows only

The plugin imports nowhere but on Windows: `winreg` is guarded, and on a machine without
it the tools answer with a clear error instead of crashing. Windows-only is declared in
the manifest.

## Testing

`python -m pytest tests/` — unit tests fake the registry and the folders, live tests
check the real machine (16 tests on the machine that produced the numbers above:
11 unit + 5 live). `VALIDATION.md` records the evidence.
