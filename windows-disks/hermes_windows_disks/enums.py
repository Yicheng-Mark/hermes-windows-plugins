"""Decoders for the storage classes' numeric enums.

``MSFT_PhysicalDisk`` / ``MSFT_Disk`` / ``MSFT_Partition`` answer with UInt16
enum values that do not change with the display language - on the writing
machine (a Chinese-language Windows 11) ``MediaType`` was ``4`` and ``BusType``
was ``17``, not translated words - so the numbers are read as they are and
decoded here. ``Win32_Volume.DriveType`` and the GPT type GUIDs carry the same
guarantee. A value the map does not know is shown as ``unknown(n)`` rather than
guessed at.
"""

from __future__ import annotations

MEDIA_TYPE = {
    0: "unspecified",
    3: "hdd",
    4: "ssd",
    5: "scm",
}

BUS_TYPE = {
    0: "unknown",
    1: "scsi",
    2: "atapi",
    3: "ata",
    4: "ieee 1394",
    5: "ssa",
    6: "fibre channel",
    7: "usb",
    8: "raid",
    9: "iscsi",
    10: "sas",
    11: "sata",
    12: "sd",
    13: "mmc",
    14: "virtual",
    15: "file-backed virtual",
    16: "storage spaces",
    17: "nvme",
}

HEALTH_STATUS = {
    0: "unknown",
    1: "healthy",
    2: "warning",
    3: "unhealthy",
}

# CIM_LogicalDevice operational states; the storage stack in practice answers
# a single-element array, [2] on a healthy disk
OPERATIONAL_STATUS = {
    0: "unknown",
    1: "other",
    2: "ok",
    3: "degraded",
    4: "stressed",
    5: "predictive failure",
    6: "error",
    7: "non-recoverable error",
    8: "starting",
    9: "stopping",
    10: "stopped",
    11: "in service",
    12: "no contact",
    13: "lost communication",
    14: "aborted",
    15: "dormant",
    16: "supporting entity in error",
    17: "completed",
    18: "power mode",
    19: "relocating",
}

PARTITION_STYLE = {
    1: "mbr",
    2: "gpt",
}

DRIVE_TYPE = {
    0: "unknown",
    1: "invalid",
    2: "removable",
    3: "fixed",
    4: "network",
    5: "cd-rom",
    6: "ram disk",
}

# MBR partition type bytes (a partition on an mbr disk carries these instead of
# a GPT GUID); the everyday ones, not a complete table
MBR_TYPE = {
    5: "extended",
    7: "installable file system (ntfs)",
    11: "fat32",
    12: "fat32x",
    14: "fat16x",
    15: "extended",
    39: "recovery / oem",
    238: "gpt protective",
}

GPT_TYPE = {
    "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}": "efi system",
    "{e3c9e316-0b5c-4db8-817d-f92df00215ae}": "microsoft reserved",
    "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}": "basic data",
    "{de94bba4-06d1-4d40-a16a-bfd50179d6ac}": "windows recovery",
    "{024dee41-33e7-11d3-9d69-0008c781f39f}": "mbr partition on a gpt disk",
    "{5808c8aa-7e8f-42e0-85d2-e1e90434cfb3}": "logical disk manager metadata",
    "{af9b60a0-1431-4f62-bc68-3311714a69ad}": "logical disk manager data",
}


def decode(table: dict[int, str], value: object) -> str:
    """One enum value into words; an unknown number says so instead of guessing."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "unknown(None)"
    return table.get(number, f"unknown({number})")


def decode_list(table: dict[int, str], values: object) -> list[str]:
    """An enum array into words (the storage stack answers a single-element list)."""
    if values is None:
        return []
    if not isinstance(values, list):
        values = [values]
    return [decode(table, item) for item in values]


def partition_kind(gpt: object, mbr: object) -> str:
    """What a partition is, from the GUID a gpt disk stamps it with.

    ``MSFT_Partition.Type`` - the friendly name a person would expect here - came
    back ``null`` for all five partitions on the writing machine, so the type is
    never read from it; the GUID is the fact that is always populated.
    """
    if isinstance(gpt, str) and gpt.strip():
        key = gpt.strip().lower()
        return GPT_TYPE.get(key, key)
    try:
        return decode(MBR_TYPE, mbr)
    except (TypeError, ValueError):
        return "unknown(None)"
