"""The device tree and the driver table, asked of CIM in two calls.

``Win32_PnPEntity`` answers with property names, enum values and ids that do not change
with the display language; the human-facing names (``Name``, ``Manufacturer``) localize,
but they are data carried through, never parsed. ``Win32_PnPSignedDriver`` is the only
place the driver behind a device is named with its version, date, signer and INF. Both
run unelevated; Device Manager's own store is not needed.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

POWERSHELL = "powershell.exe"
TIMEOUT = 90.0
# the agent talks to a person through an app window; a console must not flash over it
CREATE_NO_WINDOW = 0x08000000
# a pipe written by PowerShell may still start with a byte-order mark
_BOM = 0xFEFF

_HEADER = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;"

_DEVICES = """
$devs = Get-CimInstance Win32_PnPEntity
$out = foreach ($d in $devs) {
  [pscustomobject]@{
    name = $d.Name
    class = $d.PNPClass
    status = [string]$d.Status
    code = [int]$d.ConfigManagerErrorCode
    manufacturer = $d.Manufacturer
    device_id = $d.DeviceID
    present = if ($d.Present) { $true } else { $false }
  }
}
$out | ConvertTo-Json -Depth 4 -Compress
"""

_DRIVERS = """
$drv = Get-CimInstance Win32_PnPSignedDriver
$out = foreach ($x in $drv) {
  [pscustomobject]@{
    device_id = $x.DeviceID
    device_name = $x.DeviceName
    class = $x.DeviceClass
    version = $x.DriverVersion
    date = if ($x.DriverDate) { $x.DriverDate.ToString('o') } else { $null }
    signer = $x.Signer
    inf = $x.InfName
    signed = if ($x.IsSigned) { $true } else { $false }
    provider = $x.DriverProviderName
  }
}
$out | ConvertTo-Json -Depth 4 -Compress
"""


class PowerShellError(Exception):
    """CIM answered something other than a device listing."""


def _run(script: str) -> str:
    # the script goes in as one multi-line string: PowerShell's -Command keeps the newlines,
    # and a hashtable flattened to one line would need semicolons between every pair
    command = [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
               _HEADER + "\n" + script]
    completed = subprocess.run(command, capture_output=True, timeout=TIMEOUT,
                               creationflags=CREATE_NO_WINDOW)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()[-400:]
        raise PowerShellError(f"the CIM query failed: {detail or 'no reason given'}")
    return completed.stdout.decode("utf-8", "replace").lstrip(chr(_BOM))


def _parse(text: str, what: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"the CIM answer for {what} was not JSON: {exc}") from exc
    if isinstance(data, dict):
        data = [data]  # one object is not wrapped in a list
    if not isinstance(data, list):
        raise PowerShellError(f"the CIM answer for {what} was not a listing")
    return [item for item in data if isinstance(item, dict)]


def devices() -> list[dict[str, Any]]:
    """Every PnP device, present or historical, with its problem code."""
    return _parse(_run(_DEVICES), "devices")


def drivers() -> list[dict[str, Any]]:
    """The signed-driver table: version, date, signer and INF per device."""
    return _parse(_run(_DRIVERS), "drivers")
