# hermes-windows-updates

Answer **"what did Windows install lately, did it work, and when was this machine last
patched"** on Windows, from inside Hermes.

```python
win_update_history({"only_failures": True})
win_update_history({"query": "Defender", "count": 200})
win_hotfix_table({})
```

The update history the Settings app shows is a long list of titles with no verdicts; when
something is stuck on an old build, the answer is in there — a driver that failed three
hundred times, a feature update aborted at every attempt — but nothing in the list says so.
These two tools read the history and put the verdict in words.

## What the tools report

| Field | Where it comes from |
|---|---|
| `date`, `title`, `categories` | The update history entry, newest first (the Windows Update Agent's session interface) |
| `result` | The outcome in words: `1` still in progress, `2` succeeded, `3` succeeded with errors, `4` failed, `5` aborted |
| `hresult` | The failure's error code, masked to its unsigned `0x` spelling — the Agent hands codes over signed, so `-2145124300` shows as `0x80240034`, text a person can paste into a search box |
| `support_url` | The vendor's page for the update, when the entry carries one |

`win_hotfix_table` answers the other question — "when was the OS itself last patched" —
with the quick-fix list: KB ids, security updates, install dates and installers, newest
first. It carries OS-level updates only, and its notes say so; the full picture of what
Windows installed, Defender signatures and drivers included, is `win_update_history`'s.

## Read-only, and why it goes through PowerShell

Nothing is searched for, downloaded, installed or uninstalled: the tools query, and the
schemas say so. The history query deliberately touches only `QueryHistory` and
`GetTotalHistoryCount` — the same session object's `Search()` method is the one that goes
to the network, and it appears nowhere in this plugin.

One child process (`powershell.exe`, hidden window, 90 s timeout) per tool call; everything
else is plain Python. Dates are formatted inside PowerShell (`'o'` and `'yyyy-MM-dd'`)
because `ConvertTo-Json` serializes a `DateTime` as an epoch wrapper — or, through the CIM
wrapper, a nested object whose readable half follows the display language — neither of
which survives transport unchanged. Verified on Windows 11 (build 26300), unelevated:
723 history entries total, 500 of them fetched in 0.04 s, the quick-fix list in one CIM
call.

No network, no file writes, no elevation: everything these tools read is visible to a
normal user.

## Layout

```
plugin.yaml                        manifest: tools, tags, the read-only disclosure
hermes_windows_updates/
  tools.py                         the two tools: filtering, rows, notes
  wuquery.py                       the history and hotfix queries (PowerShell)
  resultcodes.py                   result-code and hresult words
  schemas.py                       the tools' parameter schemas
tests/test_unit.py                 every layer with fakes; no PowerShell, no COM, no CIM
tests/test_live.py                 the real Agent and CIM on this machine
```
