---
name: hermes-windows-triage
description: Triage Hermes problems that only happen on Windows or under WSL — background processes that survive a quit (orphaned stdio MCP trees, lingering python/uv/node children), WSL-to-Windows interop failures where a URL or path reaches cmd.exe unquoted, config and encoding failures (UTF-8 BOM, legacy console code pages), long-path and reserved-name errors, and terminal or keystroke differences. Use when Hermes misbehaves on Windows/WSL only, when restarts accumulate background processes, or when collecting evidence for a Windows bug report.
---

# Windows and WSL triage for Hermes

Hermes runs natively on Windows and under WSL, and both put a translation layer
between Hermes and the operating system. Most Windows-only failures are one of
four things: an argument that was treated as a shell line, a handle that lost
its width, a parent process that died first, or text that crossed an encoding
boundary. Identify which one you are looking at before proposing a fix.

Everything here is read-only until you reach step 4 of the Procedure. Do not
install, upgrade, or change Windows security settings on the user's behalf;
propose the change and let them decide.

## Quick Reference

| Symptom | First move |
|---|---|
| Background processes accumulate across restarts | `references/diagnostic-commands.md` § Orphan sweep |
| A link or file open runs an unexpected command | § Interop argv |
| `HTTP 400 "No models provided"` on first run | § Config encoding — the file almost certainly has a UTF-8 BOM |
| Crash inside `execute_code` / sandbox | Check `SYSTEMROOT` is present in the child env |
| A path works in one shell and not another | § Path forms — `/mnt/c`, `C:/`, `C:\`, and `\\wsl$` are four different strings |
| Alt+Enter does not insert a newline | Terminal owns the key; use Ctrl+Enter |
| Tests or installs are inexplicably slow | Security software scanning a fresh venv; measure before blaming Hermes |

Establish the layer first — native Windows Python, WSL Python, or the Desktop
app — because the same symptom has different causes in each:

```sh
uname -a                     # Linux kernel string + microsoft-standard => you are in WSL
echo "$WSL_DISTRO_NAME"      # non-empty only under WSL
python -c "import sys; print(sys.platform)"     # win32 => native Windows
```

The Desktop app is always a native Windows process even when the agent it
drives runs in WSL. When a report says "the desktop does X", check both layers
before concluding which one failed.

## Procedure

1. **Pin the layer and the surface.** Native Windows or WSL; CLI, `--tui`,
   gateway, or Desktop. A bug that reproduces in only one of the four surfaces
   has already eliminated most causes.
2. **Collect evidence before changing anything.** Versions, the Hermes home
   path, the exact error text, and the process tree at the moment of failure.
   `references/diagnostic-commands.md` has copy-paste commands for each.
   Ask for the *first* error, not the last: cascading errors hide the cause.
3. **Classify.** Interop (an argument crossed into `cmd.exe`), process
   lifecycle (something outlived its parent), path (the same file addressed two
   ways), encoding (bytes reinterpreted), or terminal. The Pitfalls section maps
   each class to its cause and its evidence.
4. **Change one thing.** Prefer the smallest reversible action. If the fix
   requires installing software, changing Defender exclusions, or editing the
   user's config, describe the change and ask first.
5. **Verify with the same evidence you collected in step 2** — the process tree
   is empty, the command that failed now succeeds, the config parses. A fix you
   cannot re-measure is a guess.

## Pitfalls

### Interop: argv is not a shell line

Passing a value to `cmd.exe` (or any Windows console binary) as a spawn
argument does not quote it. Node's Windows argument escaping only quotes
whitespace and quotes, so `spawn('cmd.exe', ['/c', 'start', '""', url])` hands
the URL to `cmd.exe` unquoted, and cmd re-parses it as command-line syntax:
`&`, `|`, `<`, `>`, `^`, `(`, `)`, `,`, `;`, `=` become operators, so
`https://example.com/&calc.exe` runs `calc.exe` (verified in #131561).

Two details that mislead people debugging this:

- `%NAME%` expansion happens **before** cmd applies `^` escapes, so a
  percent sign cannot be neutralized on a command line at all. It has to be
  rejected, not escaped.
- A URL that survived `new URL().toString()` cannot carry a raw space, quote or
  control character — the WHATWG parser percent-encodes them. So a "spaces in
  the URL" theory is almost always wrong; look for metacharacters instead.

Rundll32 is the usual alternative path for opening things on the Windows side
from WSL, but it changes what the user sees (no `start` semantics, different
error surfacing), so treat it as a design decision, not a drop-in fix.

### Process lifecycle: handles lose width, and jobs lose children

Two independent defects can make a Windows kill-on-close safety net look
installed while catching nothing — both verified on Windows 11 x64 (#132069):

- **Handle truncation.** Calling `AssignProcessToJobObject` through `ctypes`
  without declared argtypes marshals `GetCurrentProcess()` — the 64-bit
  pseudo-handle `0xFFFFFFFFFFFFFFFF` — as a truncated 32-bit int. The call
  fails with `ERROR_INVALID_HANDLE` (6), and a best-effort `except` arm
  swallows it. The fix is `restype = c_void_p` / explicit argtypes on every
  handle-taking call, not a retry loop.
- **Silent breakaway.** A job created with
  `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK` starts children of an attached process
  *outside* the job: `IsProcessInJob(child, job)` reads `False` for a plain
  `Popen` child. The job then contains only the attacher and kills only itself
  on close. `BREAKAWAY_OK` is the flag you want to keep — it still lets
  deliberate `CREATE_BREAKAWAY_FROM_JOB` spawns escape.

Useful trap: `IsProcessInJob(handle, NULL, ...)` returns true for essentially
every process on Windows 8+, so it cannot distinguish anything. Pass a real job
handle, and read the flags back with `QueryInformationJobObject` (there is no
`Get` variant).

### Process lifecycle: the parent dies first

When teardown kills the direct child before enumerating descendants, the
grandchildren reparent to a live process and the PPID chain that a `taskkill /T`
or a startup sweep would have followed is already broken. That is how a
`uv → .venv python → server` chain survives a quit and accumulates one copy per
restart. Detect it by comparing each candidate's `ParentProcessId` against the
set of live PIDs (see the reference file); the accumulated children usually
share a command line that names the same Hermes home.

Note that a dead parent is not by itself abnormal — `csrss.exe`, `wininit.exe`
and `explorer.exe` legitimately outlive their parents. Filter to your own
process family before calling anything an orphan.

### Config and encoding

- A `config.yaml` saved by Notepad carries a UTF-8 BOM, and the first run then
  fails with `HTTP 400 "No models provided"`. Re-save as UTF-8 **without** BOM;
  `hermes config edit` writes correctly.
- Under a legacy console code page (cp936, cp1251, cp932 …) redirected output
  and subprocess pipes can corrupt non-ASCII text. Prefer UTF-8 explicitly
  (`PYTHONUTF8=1`, `chcp 65001`, or the host's UTF-8 mode) and check with
  `Format-Hex` on the first bytes of a suspicious file rather than guessing
  from what the terminal shows.
- Windows also has quirks specific to Hermes development and testing — the
  `SYSTEMROOT`-in-sandbox failure (`WinError 10106`), the test-runner setup, and
  CRLF handling. Those are already documented in the bundled `hermes-agent`
  skill's `windows-quirks` reference file; read it instead of re-deriving them
  here.

### Path forms

The same file has several spellings, and they are not interchangeable:
`C:\Users\me\x`, `C:/Users/me/x`, `/mnt/c/Users/me/x` (WSL), `\\wsl$\<distro>\home\me\x`
(Windows reaching into WSL). Translate explicitly with `wslpath -w` / `wslpath -u`
instead of string-replacing separators. Paths longer than 260 characters fail
unless long-path support is enabled, and reserved device names (`CON`, `PRN`,
`AUX`, `NUL`, `COM1`…`COM9`, `LPT1`…`LPT9`) are still special — including with
an extension. Trailing dots and spaces are stripped silently, so a path that
"exists" when written can fail when read back.

## Verification

A Windows fix is verified when the evidence changes, not when the error stops
appearing:

- **Orphans:** the process sweep returns nothing for the Hermes family after a
  clean quit and restart cycle — not merely fewer entries.
- **Interop:** the action that previously concatenated a command now either
  performs the open or refuses it with a log line and no spawn; a URL carrying
  `&` no longer reaches a shell as an operator.
- **Job objects:** after the fix, a plain child of the attached process reads
  `IsProcessInJob(child, <real job handle>) == True`, and the job's limit flags
  read back without the silent-breakaway bit.
- **Config:** the first 3 bytes of the file are not `EF BB BF`, and the
  original failing request now succeeds against the same config.

If the evidence is unchanged, the diagnosis was wrong — return to step 3 with
the new evidence rather than adding a second change on top.
