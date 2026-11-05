r"""Windows Update history and hotfixes, one call each.

``Microsoft.Update.Session`` answers the update history the Settings app shows — the
newest first, 723 entries on the validation machine, 0.04 s for 500 of them — with
result codes that do not change with the display language. ``Get-CimInstance
Win32_QuickFixEngineering`` answers the OS-level hotfix list. Dates are formatted
inside PowerShell (``'o'`` and ``'yyyy-MM-dd'``) because ``ConvertTo-Json`` serializes a
DateTime as an epoch wrapper ``\/Date(...)\/`` — or, through the CIM wrapper, a nested
object whose readable half is localized — neither of which survives transport unchanged.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

POWERSHELL = "powershell.exe"
TIMEOUT = 90.0
# the agent talks to a person through an app window; a console must not flash over it
CREATE_NO_WINDOW = 0x08000000
# a pipe written by PowerShell may still start with a byte-order mark
_BOM = 0xFEFF

MAX_HISTORY = 500  # the API takes a range, not the whole store; 500 is its useful ceiling

_HEADER = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;"

# QueryHistory only reads what was already installed or attempted; the searcher's
# Search() method is the one that goes to the network, and it is not called anywhere.
_HISTORY = """
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$total = $searcher.GetTotalHistoryCount()
if ($total -lt 1) { '{"total": 0, "entries": []}'; exit 0 }
$take = [int]$env:HERMES_WU_TAKE
if ($take -lt 1) { $take = 1 }
if ($take -gt 500) { $take = 500 }
if ($take -gt $total) { $take = $total }
$entries = $searcher.QueryHistory(0, $take)
$out = foreach ($e in $entries) {
  [pscustomobject]@{
    date = if ($e.Date -and $e.Date.Year -gt 1) { $e.Date.ToString('o') } else { $null }
    title = $e.Title
    result_code = [int]$e.ResultCode
    hresult = [int]$e.HResult
    support_url = $e.SupportUrl
    categories = @($e.Categories | ForEach-Object { $_.Name })
  }
}
@{ total = [int]$total; entries = @($out) } | ConvertTo-Json -Depth 4 -Compress
"""

_HOTFIX = """
$qfe = Get-CimInstance Win32_QuickFixEngineering
$out = foreach ($k in $qfe) {
  [pscustomobject]@{
    id = $k.HotFixID
    description = $k.Description
    installed_on = if ($k.InstalledOn -and $k.InstalledOn.Year -gt 1) { $k.InstalledOn.ToString('yyyy-MM-dd') } else { $null }
    installed_by = $k.InstalledBy
  }
}
if ($out) { $out | ConvertTo-Json -Depth 4 -Compress } else { '[]' }
"""


class PowerShellError(Exception):
    """The Windows Update Agent or CIM answered something other than a listing."""


def _run(script: str, take: int | None = None) -> str:
    # the script goes in as one multi-line string: PowerShell's -Command keeps the newlines,
    # and a hashtable flattened to one line would need semicolons between every pair
    command = [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
               _HEADER + "\n" + script]
    env = None
    if take is not None:
        # the row count reaches the query through the environment, not the command
        # line: no quoting, escaping or injection surface at all
        env = {**os.environ, "HERMES_WU_TAKE": str(int(take))}
    completed = subprocess.run(
        command,
        capture_output=True,
        timeout=TIMEOUT,
        creationflags=CREATE_NO_WINDOW,
        env=env,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()[-400:]
        raise PowerShellError(f"the Windows Update query failed: {detail or 'no reason given'}")
    return completed.stdout.decode("utf-8", "replace").lstrip(chr(_BOM))


def _as_list(data: Any) -> list[dict]:
    if isinstance(data, dict):
        data = [data]  # one object is not wrapped in a list
    if not isinstance(data, list):
        raise PowerShellError("the answer was not a listing")
    return [item for item in data if isinstance(item, dict)]


def history(take: int = MAX_HISTORY) -> dict[str, Any]:
    """The newest updates the machine installed or attempted, newest first."""
    text = _run(_HISTORY, take=take)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"the history answer was not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PowerShellError("the history answer was not a history")
    entries = data.get("entries")
    if isinstance(entries, dict):
        entries = [entries]  # one entry is not wrapped in a list either
    if not isinstance(entries, list):
        entries = []
    return {"total": int(data.get("total") or 0),
            "entries": [item for item in entries if isinstance(item, dict)]}


def hotfixes() -> list[dict[str, Any]]:
    """The OS-level hotfixes, KB numbers and install dates."""
    text = _run(_HOTFIX)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"the hotfix answer was not JSON: {exc}") from exc
    return _as_list(data)
