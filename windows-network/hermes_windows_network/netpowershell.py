"""The machine's network adapters and their IP configuration, from the NetAdapter cmdlets.

Two facts decided the shape of this module, both checked on a machine whose display
language is Chinese:

- ``Get-NetAdapter`` answers through ``ConvertTo-Json`` with field names and *enum*
  values that do not change with the display language ("Up", "Disconnected",
  "Not Present"): the adapter's own ``Name`` is localized ("以太网"), so it is carried
  as data and never parsed. ``netsh`` and the ``ipconfig`` prose are localized and
  would have made the tool lie on every non-English machine.
- ``Get-NetIPConfiguration -InterfaceIndex N`` *throws* for an adapter IP is not
  bound to (a Hyper-V host adapter), so the detail call lists every configuration
  once and filters in PowerShell instead of asking for one index by parameter.

The link speed is read as ``ReceiveLinkSpeed`` (a number of bits per second) rather
than ``LinkSpeed`` (a display string such as "2.5 Gbps" that follows the display
language).
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

POWERSHELL = "powershell.exe"
TIMEOUT = 60.0
# the agent talks to a person through an app window; a console must not flash over it
CREATE_NO_WINDOW = 0x08000000
# a pipe written by PowerShell may still start with a byte-order mark
_BOM = 0xFEFF

_HEADER = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;"

# `DriverDate` arrives as a string on some adapters and as a DateTime on others, so
# the cast is tried rather than assumed; an adapter with no driver answers "".
_ADAPTERS = """
$adapters = foreach ($a in Get-NetAdapter) {
  [pscustomobject]@{
    name = $a.Name
    description = $a.InterfaceDescription
    if_index = $a.ifIndex
    status = [string]$a.Status
    mac = $a.MacAddress
    link_speed_bps = $a.ReceiveLinkSpeed
    media_type = [string]$a.MediaType
    virtual = [bool]$a.Virtual
    driver_version = $a.DriverVersion
    driver_date = try { ([datetime]$a.DriverDate).ToString('o') } catch { [string]$a.DriverDate }
  }
}
$adapters | ConvertTo-Json -Depth 4 -Compress
"""

# One listing of every IP configuration, filtered in PowerShell: asking for a single
# index by parameter throws when IP is not bound to that adapter. DNS is asked of
# `Get-DnsClientServerAddress` because the configuration object's own DNS section
# is empty on adapters that have servers configured but no lease (a disconnected
# cable with a static DNS left behind), which is exactly the case a person asks about.
# AddressFamily is compared numerically: 2 is IPv4, 23 is IPv6, and neither is a word.
_CONFIG = """
$idx = <INDEX>
$cfg = Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.InterfaceIndex -eq $idx }
$dnsRows = Get-DnsClientServerAddress -InterfaceIndex $idx -ErrorAction SilentlyContinue
[pscustomobject]@{
  if_index = $idx
  found = [bool]$cfg
  ipv4 = @(if ($cfg) { @($cfg.IPv4Address | ForEach-Object { @{ address = $_.IPAddress; prefix = $_.PrefixLength; origin = [string]$_.PrefixOrigin } }) })
  ipv6 = @(if ($cfg) { @($cfg.IPv6Address | ForEach-Object { $_.IPAddress }) })
  gateway4 = ($cfg.IPv4DefaultGateway | Select-Object -First 1).NextHop
  gateway6 = ($cfg.IPv6DefaultGateway | Select-Object -First 1).NextHop
  dns4 = @(($dnsRows | Where-Object { $_.AddressFamily -eq 2 }).ServerAddresses)
  dns6 = @(($dnsRows | Where-Object { $_.AddressFamily -eq 23 }).ServerAddresses)
} | ConvertTo-Json -Depth 5 -Compress
"""


class PowerShellError(Exception):
    """PowerShell is missing, slow, or answered something this module cannot use."""


def run(script: str, timeout: float = TIMEOUT) -> Any:
    """PowerShell's JSON answer, parsed; every way it can fail comes back as PowerShellError."""
    argv = [
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    try:
        finished = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except FileNotFoundError as exc:
        raise PowerShellError(f"PowerShell is not on PATH: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PowerShellError(f"PowerShell did not answer within {timeout:.0f}s") from exc
    text = finished.stdout.decode("utf-8", errors="replace").lstrip(chr(_BOM)).strip()
    if finished.returncode != 0:
        complaint = finished.stderr.decode("utf-8", errors="replace").strip()
        raise PowerShellError(
            f"PowerShell exited {finished.returncode}: {(complaint or text)[:400]}"
        )
    if not text:
        raise PowerShellError("PowerShell answered nothing")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"PowerShell's answer was not JSON: {text[:200]}") from exc


def adapters(timeout: float = TIMEOUT) -> list[dict[str, Any]]:
    """Every visible network adapter: its name, state, speed, and its driver."""
    answer = run(_HEADER + _ADAPTERS, timeout)
    if isinstance(answer, dict):  # -Compress writes one object rather than a one-row array
        answer = [answer]
    if not isinstance(answer, list):
        raise PowerShellError(f"expected a list of adapters, got {type(answer).__name__}")
    return [row for row in answer if isinstance(row, dict)]


def configuration(if_index: int, timeout: float = TIMEOUT) -> dict[str, Any]:
    """One adapter's IP configuration: addresses, gateways and the DNS servers."""
    if not isinstance(if_index, int) or if_index < 0:
        raise PowerShellError(f"not an interface index: {if_index!r}")
    script = _HEADER + _CONFIG.replace("<INDEX>", str(if_index))
    answer = run(script, timeout)
    if not isinstance(answer, dict):
        raise PowerShellError("expected an object with the configuration")
    # a list this module asks for can still arrive unwrapped: one row becomes a bare
    # object and none becomes {} -- both are the list they meant
    for key in ("ipv4", "ipv6", "dns4", "dns6"):
        value = answer.get(key)
        if value is None or value == {}:
            answer[key] = []
        elif not isinstance(value, list):
            answer[key] = [value]
    return answer


__all__ = ["PowerShellError", "adapters", "configuration", "run"]
