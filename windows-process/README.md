# hermes-windows-process

Answer **"what is still running, and who started it"** on Windows, from inside Hermes.

```python
win_process_table({"process": "hermes"})
win_process_table({"orphans_only": True, "include_system": False})
win_process_table({"pid": 21432, "with_ancestry": True})
```

The tool reads the same process rows Task Manager does — `CreateToolhelp32Snapshot` gives
PID, parent PID, image name and thread count — then opens each process read-only for its
image path and **start time**. That last field is what makes the parent column mean
something: Windows stores a parent *PID*, not a handle, so once the parent exits its PID is
free for reuse, and a child that outlived it points at an unrelated newer process. A parent
that started **after** its child cannot have spawned it.

| `parent_state` | Meaning |
|---|---|
| `alive` | The parent PID belongs to a process that started before this one — the real parent. |
| `gone` | No process holds that PID any more: the parent exited and this one kept running. |
| `reused` | The PID is in use, but by a process that started later, so the original parent is gone. |
| `unknown` | The parent row exists but one of the two start times could not be read. |
| `root` | Parent PID 0 — the top of the table. |

## Output

```json
{
  "ok": true,
  "matched": 2,
  "total_processes": 308,
  "orphans": 9,
  "orphans_gone": 9,
  "orphans_reused": 0,
  "entries": [
    {"pid": 10004, "parent_pid": 8640, "process": "cc-switch.exe",
     "path": "C:\\Users\\warri\\AppData\\Local\\Programs\\CC Switch\\cc-switch.exe",
     "started": "2026-10-24T14:19:31Z", "age_seconds": 41040, "threads": 12,
     "parent_process": null, "parent_state": "gone", "system": false}
  ],
  "ancestry": [],
  "notes": ["2 of 308 process(es) matched"]
}
```

Ordering puts the oldest process first, which is how you find the survivor rather than the
thing you just started. `ancestry` carries the chain up to the top of the table for each
matched PID when `with_ancestry` is set, marked `context: true`.

## Filters

| Argument | Effect |
|---|---|
| `pid` / `pids` | Match specific process IDs. |
| `process` | Case-insensitive substring of the image name **or** path. |
| `parent` | Only processes whose parent PID is this value. |
| `orphans_only` | Only `gone` and `reused` — what outlived its parent. |
| `with_ancestry` | Add the ancestor chain of each match. |
| `include_system` | Default `true`. `false` drops images under the Windows directory and processes this account cannot open. |
| `limit` | Default 100, max 500. |

Session and bootstrap processes (`csrss`, `wininit`, `winlogon`, `services`, `explorer`) are
started by a parent that exits by design, so they always read `gone` without being a leak.
They are flagged `system: true`, and the notes say how many of the flagged rows are theirs.

## What it does not do

- **No command lines.** Reading another process's command line on Windows means reading its
  memory (the PEB) through `ReadProcessMemory`. This plugin does not read process memory, so
  it reports the image path and start time instead. `wmic process get commandline` or
  PowerShell's `Get-CimInstance Win32_Process` still answer that, at a second or more per
  call and with a child process spawned each time.
- **No killing.** Terminating a PID that may have been reused is a good way to kill the
  wrong thing; the tool is read-only on purpose.
- **No job-object membership.** `IsProcessInJob(handle, NULL)` answers `true` for every
  process on Windows 8 and later (the system root job), so it cannot be used to tell whether
  a child would die with its parent.

## Install

```bash
git clone https://github.com/Yicheng-Mark/hermes-windows-plugins /tmp/hermes-windows-plugins
cp -r /tmp/hermes-windows-plugins/windows-process ~/.hermes/plugins/hermes-windows-process
hermes plugins enable hermes-windows-process
```

Or install the catalog entry by name once it is listed: `hermes plugins install hermes-windows-process`.

## Disclosures

The tool reads the process table and each process's image path and creation time, and hands
them to the model: image names and paths routinely carry the user name
(`C:\Users\<name>\...`), and the ancestry chain shows which editor, shell or agent started
which process. Treat the output like the Task Manager screenshot it replaces.

Everything is read-only: `PROCESS_QUERY_LIMITED_INFORMATION` only, no memory reads, no
handle duplication, no inheritance, no writes, no child processes, no network calls, no file
writes, no self-update. Stdlib-only (`ctypes` against kernel32).

## Tests

```bash
python -m pytest tests/     # 14 unit + 4 live; the live ones skip off Windows
```

## License

MIT.
