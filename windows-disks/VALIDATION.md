# VALIDATION — what was measured, not assumed

Machine: Windows 11 Home China (Chinese display language), one UMIS NVMe SSD,
GPT, five partitions, four volumes (C:, D:, WINRE_DRV, SYSTEM_DRV), unelevated.

## Source decisions, each from a live probe (2026-11-07)

- **`MSFT_PhysicalDisk` is the disk source.** All fields populated:
  `MediaType` arrived as the number 4 (ssd), `BusType` 17 (nvme),
  `HealthStatus` 0, `OperationalStatus` [2], `SpindleSpeed` 0, exact size.
  The enums are numbers on a Chinese-language install — the display language
  never reaches the answer.
- **`HealthStatus` can read `unknown` (0) on a healthy NVMe.** The probe's disk
  is healthy and answers exactly that, while `OperationalStatus` says `[2]`
  (ok). Both are reported; the notes and the detail's health sentence say so
  whenever the word is unknown. Unknown is not treated as failing.
- **`MSFT_Disk.PartitionStyle`**: 2 on this GPT disk; decoded as
  1=mbr, 2=gpt.
- **`MSFT_Partition.Type` is never populated** — `null` for all five
  partitions. Same shape as the services plugin's never-filled CIM fields. The
  partition kind is decoded from the GPT type GUID instead (always populated);
  on an mbr disk, from the `MbrType` byte. The five real GUIDs here decode to
  efi system / microsoft reserved / basic data ×2 / windows recovery.
- **`Win32_DiskDrive` is not read**: `Partitions` said 4 against 5 real
  partitions (stale), `InterfaceType` said SCSI for an NVMe (the known WMI
  quirk), `MediaType` is a string with no enum guarantee.
- **`Win32_Volume` is the volume source**: it lists the letterless volumes
  (EFI, WINRE) that `Win32_LogicalDisk` hides. `Win32_LogicalDisk` is not read
  at all — its `Description` is localized text ("本地固定磁盘").
- **`Win32_NetworkConnection`** supplies the UNC behind a mapped drive (empty
  list on this machine right now; the fixture covers the populated shape).
- **Disk ↔ volume link**: `MSFT_Partition.DriveLetter` (`C`) matches
  `Win32_Volume.DriveLetter` (`C:`) case-insensitively after stripping the
  colon — the probe shows both spellings on one machine.
- **PowerShell unwrapping**: with one disk, `physical`/`disks`/`parts`
  arrived as bare objects (the probe's own output proves it). The query wraps
  every array in `@(...)` and the parser additionally normalizes either shape
  — a unit test feeds bare objects end-to-end.

## Encoding

`[Console]::OutputEncoding=[Text.Encoding]::UTF8` heads the script (the
services pattern); the reader decodes UTF-8 and strips a leading BOM.

## Measurements

- one full query session (five CIM classes): **626 ms** cold from Python
- table build on the query's answer: ~0.5 ms; a second table call runs its own
  session at the same ~0.6 s
- every call spawns `powershell.exe -NoProfile -NonInteractive` with
  `CREATE_NO_WINDOW`; timeout 90 s

## Tests

30 passed (25 unit + 5 live), `python -m pytest -q`, 4.0 s, no network, no
elevation. Unit fixtures are the probe's real shapes (the writing machine's
answer is one of them verbatim, including health=0/op=[2]) plus a three-disk
fixture covering mbr type bytes, a warning disk, a removable and a network
volume with a UNC, the free-space thresholds (4.2 % critical, 9.4 % low) and
unknown enum numbers (99 → "unknown(99)").

## Read-only disclosure

The tools read the storage classes and the mapped-drive table through one
PowerShell CIM session and report what they answered. Nothing is
defragmented, formatted, resized, checked or repaired; nothing is written; no
elevation; no network calls of the plugin's own. Serial numbers and volume
labels are reported as data, the same page a person sees in Disk Management.
