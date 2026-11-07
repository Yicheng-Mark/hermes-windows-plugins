# hermes-windows-disks

Read-only disk and volume health tools for Hermes on Windows: what the storage
stack itself says about every disk and every volume, in one PowerShell CIM
session, with the numeric enums decoded into words.

## Tools

### `win_disk_table`

Answer "are this machine's disks healthy, and which volume is filling up":

- every **disk** — model, serial, media (ssd / hdd / scm), bus (nvme, sata, usb,
  …), size, the storage stack's health word, GPT or MBR, boot/system flags,
  partition count
- every **volume** — drive letter, label, file system, capacity, free space with
  its percentage and a verdict (critical under 5 %, low under 10 %), drive type
  (fixed / removable / network / cd-rom), the local disk a volume lives on, and
  the UNC path behind a mapped network drive

Volumes without a drive letter (EFI system, recovery, WINRE) are hidden unless
`include_letterless` is set; `kind` narrows to disks or volumes; `query` filters
by model, serial, letter, label or file system. The notes call out every disk
that reports warning or unhealthy, the "unknown" health word (see below), and
every volume below 10 % free.

### `win_disk_detail`

One disk or one volume in full, by `target` — a drive letter (`C:` or `C`), a
volume label, a disk model, a serial number, or a disk number (`0`, `disk 0`):

- a **volume** — every fact above, the free-space verdict in words, and the
  owning disk's health beside it; a network volume names its UNC path
- a **disk** — health in words, the partition layout decoded from each
  partition's GUID type (efi system, microsoft reserved, basic data, windows
  recovery) with size, offset and letter, its volumes with their free space,
  the largest contiguous free extent, and the spindle speed where there is one

## The "unknown" health word

`MSFT_PhysicalDisk.HealthStatus` answered `0` (unknown) on the writing
machine's perfectly healthy NVMe — not a fault. When the word reads unknown,
both signals are shown: the health word and `OperationalStatus` (which said
`ok`), and the notes say exactly that.

## Cost and reach

One PowerShell session per call (~0.6 s on the writing machine, one NVMe disk,
five partitions, four volumes). Read-only: the storage classes are queried and
nothing is defragmented, formatted, resized, checked or repaired; no writes, no
elevation, no network calls of its own, no Python dependencies. Windows only.

## Install

Clone this directory into `~/.hermes/plugins/hermes-windows-disks` (or
`hermes plugins install`), then:

    hermes plugins enable hermes-windows-disks

Tests: `python -m pytest` from this directory (25 unit with fakes, 5 live on a
real machine).
