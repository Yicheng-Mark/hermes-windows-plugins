# hermes-windows-apps

Answer **"what is installed on this machine"** on Windows, from inside Hermes.

```python
win_app_table({"query": "visual c++"})
win_app_table({"view": "user-64"})
win_app_detail({"name": "OBS Studio"})
```

The Apps & Features question, answered without opening Settings: every program
the four Uninstall registry keys carry -- the machine's 64-bit and 32-bit views
plus the user's -- which is a superset of what Settings shows, because it
includes the entries publishers asked to hide and the per-user installs the
machine page never lists.

## What the tools report

| Field | Where it comes from |
|---|---|
| `name`, `version`, `publisher` | The program's `DisplayName`, `DisplayVersion`, `Publisher` values, verbatim |
| `view` | Which Uninstall key the entry lives in: `machine-64`, `machine-32`, `user-64`, `user-32` |
| `views` | Present when the same name is registered in several views -- the 32/64-bit dual install, listed once |
| `size_mb` | `EstimatedSize`, a DWORD the publisher writes in kilobytes, surfaced as MB |
| `installed` | `InstallDate`, written as `YYYYMMDD` or a localized date; both are read |
| `hidden` | `SystemComponent` = 1: the publisher asked Apps & Features not to show it (runtimes, update rollups); filtered out unless `include_system_components` is set |

`win_app_detail` adds every remaining field the publisher wrote -- install
location checked against disk, help and about links, comments, the
no-modify/no-repair locks -- and a reading of the uninstall command: an MSI
product code, the publisher's own setup executable, an appx removal, or a
script. A program whose recorded folder is gone on disk is flagged: that is an
uninstall that left its registration behind.

## Read-only, and why it goes through the registry

Nothing is uninstalled, modified or run: the tools enumerate registry values,
and the uninstall string is classified and quoted, never executed.

The registry answers in well under a second on this machine with no PowerShell
spawn and no WMI query. `Win32_Product` costs both, sees only MSI packages,
and reconfigures each one while enumerating -- a documented side effect that
can trigger installer self-repair -- which is why this plugin never touches
it.

## Windows only

The plugin imports nowhere but on Windows: `winreg` is guarded, and on a
machine without it the tools answer with a clear error instead of crashing.
Windows-only is declared in the manifest.

## Testing

`python -m pytest tests/` -- unit tests fake the registry through an injected
opener and a `winreg` import blocker, live tests check the real machine.
`VALIDATION.md` records the evidence.
