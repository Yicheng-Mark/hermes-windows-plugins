"""Every service, asked of CIM in one call.

``Get-CimInstance Win32_Service`` answers with property names and enum values that do not
change with the display language (``State`` is ``Stopped`` on a Chinese install too), unlike
``sc.exe query``, whose labels and status words are localized. One call carries the state,
start mode, delayed-autostart flag, pid, exit code, account, binary path and description;
the dependency and failure-recovery facts are not in CIM truthfully and come from the
registry (see svcreg).
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

_HEADER = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;"

_LIST = """
$svcs = Get-CimInstance Win32_Service
$out = foreach ($s in $svcs) {
  [pscustomobject]@{
    name = $s.Name
    display = $s.DisplayName
    state = [string]$s.State
    start = [string]$s.StartMode
    delayed = if ($s.DelayedAutoStart) { $true } else { $false }
    pid = if ($s.ProcessId) { [int]$s.ProcessId } else { 0 }
    exit_code = [int]$s.ExitCode
    account = $s.StartName
    binary = $s.PathName
    description = $s.Description
  }
}
$out | ConvertTo-Json -Depth 4 -Compress
"""

_EVENTS = """
$name = $env:HERMES_SVC_NAME
$ids = @(7000, 7001, 7009, 7011, 7023, 7024, 7031, 7034, 7045)
$events = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Service Control Manager'} `
  -MaxEvents 400 -ErrorAction SilentlyContinue |
  Where-Object { $ids -contains $_.Id -and $_.Message -match [regex]::Escape($name) } |
  Select-Object -First 12
$out = foreach ($e in $events) {
  [pscustomobject]@{
    time = $e.TimeCreated.ToString('o')
    id = [int]$e.Id
    what = $e.Message
  }
}
if ($out) { $out | ConvertTo-Json -Depth 4 -Compress } else { '[]' }
"""


class PowerShellError(Exception):
    """CIM answered something other than a service listing."""


def _run(script: str, service_name: str | None = None) -> str:
    # the script goes in as one multi-line string: PowerShell's -Command keeps the newlines,
    # and a hashtable flattened to one line would need semicolons between every pair
    command = [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
               _HEADER + "\n" + script]
    env = None
    if service_name is not None:
        # the service name reaches the event query through the environment, not the
        # command line: no quoting, escaping or injection surface at all
        env = {**os.environ, "HERMES_SVC_NAME": service_name}
    completed = subprocess.run(
        command,
        capture_output=True,
        timeout=TIMEOUT,
        creationflags=CREATE_NO_WINDOW,
        env=env,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()[-400:]
        raise PowerShellError(f"the CIM query failed: {detail or 'no reason given'}")
    return completed.stdout.decode("utf-8", "replace").lstrip(chr(_BOM))


def _parse(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"the CIM answer was not JSON: {exc}") from exc
    if isinstance(data, dict):
        data = [data]  # one object is not wrapped in a list
    if not isinstance(data, list):
        raise PowerShellError("the CIM answer was not a service listing")
    return [item for item in data if isinstance(item, dict)]


def services() -> list[dict[str, Any]]:
    """Every registered service, with the facts CIM tells the truth about."""
    return _parse(_run(_LIST))


def failures(name: str) -> list[dict[str, Any]]:
    """The SCM event-log failures and installs that name this service."""
    text = _run(_EVENTS, service_name=name)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [item for item in data if isinstance(item, dict)]
