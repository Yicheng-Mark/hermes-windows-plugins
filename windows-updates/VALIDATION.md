# Validation

What was checked before this plugin was submitted, on which machine, and what the numbers
were. Everything below was run on Windows 11 (build 26300, Chinese display language),
Python 3.13, unelevated, against the `hermes-agent` admission validator.

## Admission checks

`validate_plugin_dir` reports all 15 checks pass, security scan safe, zero warnings, on
this directory. The plugin suite is **23 passed** (16 unit, 7 live) on this machine; the
same suite runs inside the pin tarball before the entry is submitted.

## What the Windows Update Agent answers, and how fast

Measured on this machine, unelevated, through the session interface (`QueryHistory` /
`GetTotalHistoryCount` only — the searcher's `Search()` method is the networked one and
appears nowhere in this plugin):

- **723 history entries** in total; the newest 500 fetched in **0.035 s** (the first call
  pays ~0.26 s of COM session startup).
- The newest entry is a Defender signature update (`KB2267602`, version 1.463.121.0)
  dated `2026-11-04T13:28:06` — the same stream Settings > Windows Update > Update
  history renders, newest first.
- **128 of the newest 500 entries did not end clean** (Defender signature updates
  failing repeatedly is the common shape on this machine). A sample failure: ResultCode
  `4`, HResult handed over **signed** as `-2145124300`, which the tool shows masked to
  its unsigned spelling `0x80240034`.
- The quick-fix list (`Win32_QuickFixEngineering`): 7 entries on this machine, all dated,
  newest install date 2026-10-18; one CIM call.

## Three transport traps, handled inside PowerShell

All three were observed on this machine before the parsing was written:

- **`ConvertTo-Json` does not carry a DateTime.** From the COM side a date serializes as
  the epoch wrapper `\/Date(1793770086000)\/`; through the CIM wrapper it serializes as a
  nested object whose readable half follows the display language (`"2026年10月18日"`).
  Dates are formatted inside PowerShell instead — `'o'` for history timestamps,
  `'yyyy-MM-dd'` for hotfix install dates — so what crosses the pipe is a fixed string.
- **`HResult` is a signed 32-bit integer** on the way out (`-2145124300` for a failure).
  It is masked to the unsigned `0x` form, the same convention the services plugin uses
  for Win32 exit codes.
- **A one-element collection is not wrapped in a list** by `ConvertTo-Json` (and one
  history entry arrives as a bare object). Both query and tool layers re-wrap, and a unit
  test covers each.

## Language independence

Titles localize with the display language (the sample above is Chinese); the result codes,
the hotfix fields and the CIM property names do not. Nothing in the plugin parses a
localized word: filters match on ids and titles the caller supplies, and every verdict
comes from an API-fixed integer.

## What a person sees

- `win_update_history({"count": 50})` on this machine: the 50 newest installs with their
  verdicts, a note that 723 exist, and a count of how many in the window did not end
  clean.
- `win_update_history({"only_failures": True, "count": 500})`: the 128 not-clean endings,
  each with its `0x` code.
- `win_hotfix_table({})`: 7 KBs, newest first, with the note that the quick-fix list
  carries OS-level updates only.

A machine with no update history at all (fresh install, history cleared) is an answer —
an empty list with `total = 0` — not an error; a machine whose Windows Update service is
disabled answers with a clean `history_unavailable` error carrying the Agent's own
message.
