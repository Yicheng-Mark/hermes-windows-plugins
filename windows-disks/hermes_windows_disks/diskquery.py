"""The storage stack's own view, asked in one PowerShell session.

``MSFT_PhysicalDisk`` / ``MSFT_Disk`` / ``MSFT_Partition`` (namespace
``root/Microsoft/Windows/Storage``) carry the health, bus and partition-style
facts as numeric enum values that do not move with the display language;
``Win32_Volume`` sees the volumes without a drive letter (EFI, recovery) that
``Win32_LogicalDisk`` hides; ``Win32_NetworkConnection`` holds the UNC path
behind a mapped drive. One session runs every query and answers a single JSON
object, so a table costs one PowerShell start (~a second) however much it reads.

What was measured on the writing machine and shaped this file: the friendly
``MSFT_Partition.Type`` came back ``null`` for every partition (the GUID type is
always populated instead), ``Win32_DiskDrive.Partitions`` undercounted 4 against
5 real partitions (stale - ``MSFT_Disk.NumberOfPartitions`` is the live count),
and ``Win32_LogicalDisk.Description`` is localized text ("本地固定磁盘") - none of
the three is read.
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

# one wrapper object with five arrays: @(...) keeps PowerShell from unwrapping a
# single-element array into a bare object (the trap that hits ConvertTo-Json on
# one-disk machines); the empty netconn list is @() by the if, not $null
_QUERY = """
$phys = Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_PhysicalDisk
$mdsk = Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_Disk
$part = Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_Partition
$vols = Get-CimInstance Win32_Volume
$netc = Get-CimInstance Win32_NetworkConnection -ErrorAction SilentlyContinue
$physical = @(foreach ($p in $phys) { [pscustomobject]@{
  id = [string]$p.DeviceId; model = $p.FriendlyName; serial = $p.SerialNumber
  media = [int]$p.MediaType; bus = [int]$p.BusType; health = [int]$p.HealthStatus
  op = @($p.OperationalStatus | ForEach-Object { [int]$_ })
  size = [int64]$p.Size; spindle = [int]$p.SpindleSpeed } })
$disks = @(foreach ($d in $mdsk) { [pscustomobject]@{
  number = [int]$d.Number; style = [int]$d.PartitionStyle; guid = $d.Guid
  boot = [bool]$d.IsBoot; system = [bool]$d.IsSystem; readonly = [bool]$d.IsReadOnly
  partitions = [int]$d.NumberOfPartitions; free_extent = [int64]$d.LargestFreeExtent
  size = [int64]$d.Size } })
$parts = @(foreach ($t in $part) { [pscustomobject]@{
  disk = [int]$t.DiskNumber; partition = [int]$t.PartitionNumber
  letter = $t.DriveLetter; offset = [int64]$t.Offset; size = [int64]$t.Size
  gpt = $t.GptType; mbr = $t.MbrType
  boot = [bool]$t.IsBoot; system = [bool]$t.IsSystem } })
$volumes = @(foreach ($v in $vols) { [pscustomobject]@{
  letter = $v.DriveLetter; label = $v.Label; fs = $v.FileSystem
  capacity = [int64]$v.Capacity; free = [int64]$v.FreeSpace
  drive_type = [int]$v.DriveType; guid = $v.DeviceID } })
$netconns = @(if ($netc) { foreach ($n in $netc) { [pscustomobject]@{
  local = $n.LocalName; remote = $n.RemoteName; status = $n.Status } } })
[pscustomobject]@{ physical = $physical; disks = $disks; parts = $parts
  volumes = $volumes; netconns = $netconns } | ConvertTo-Json -Depth 5 -Compress
"""


class PowerShellError(Exception):
    """The storage query answered something other than a disk and volume listing."""


def _run(script: str) -> str:
    # the script goes in as one multi-line string: PowerShell's -Command keeps the newlines,
    # and a hashtable flattened to one line would need semicolons between every pair
    command = [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
               _HEADER + "\n" + script]
    completed = subprocess.run(
        command,
        capture_output=True,
        timeout=TIMEOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()[-400:]
        raise PowerShellError(f"the storage query failed: {detail or 'no reason given'}")
    return completed.stdout.decode("utf-8", "replace").lstrip(chr(_BOM))


def _rows(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):  # one object is not wrapped in a list
        value = [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def query() -> dict[str, list[dict[str, Any]]]:
    """Every disk, partition and volume the storage stack reports, once."""
    try:
        data = json.loads(_run(_QUERY))
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"the storage answer was not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PowerShellError("the storage answer was not a listing")
    return {key: _rows(data.get(key)) for key in
            ("physical", "disks", "parts", "volumes", "netconns")}
