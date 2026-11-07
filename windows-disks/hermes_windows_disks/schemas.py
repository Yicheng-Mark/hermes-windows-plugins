"""Tool schemas for the two disk tools."""

DISK_TABLE = {
    "name": "win_disk_table",
    "description": (
        "Answer 'are this machine's disks healthy, and which volume is filling "
        "up': every physical disk (model, serial, SSD/HDD/SCM, bus - nvme, "
        "sata, usb -, size, health word, GPT or MBR, boot/system flags, "
        "partition count) and every volume (drive letter, label, file system, "
        "capacity, free space with its percentage, fixed/removable/network/"
        "cd-rom, the disk a volume lives on, the UNC path behind a mapped "
        "drive) in one table. Volumes without a drive letter (EFI, recovery, "
        "WINRE) are hidden unless include_letterless is set. The health word "
        "'unknown' is what the storage stack reports on a perfectly healthy "
        "NVMe - when it appears, OperationalStatus is the other signal and the "
        "notes say so. Use it for 'why is the disk slow', 'will this drive "
        "fail', 'where did the space go'. Read-only: nothing is "
        "defragmented, formatted, resized, checked or repaired. Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": (
                    "Rows to return: 'disk', 'volume', or 'all' (default "
                    "'all')."
                ),
            },
            "include_letterless": {
                "type": "boolean",
                "description": (
                    "Also list the volumes without a drive letter - EFI "
                    "system, recovery, the odd unlettered data volume "
                    "(default false, they are noise for 'where did the space "
                    "go')."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring against a disk's model or "
                    "serial, or a volume's letter, label or file system, e.g. "
                    "'C:', 'Data', 'nvme', 'NTFS'."
                ),
            },
        },
    },
}

DISK_DETAIL = {
    "name": "win_disk_detail",
    "description": (
        "One disk or one volume read in full: the health in words (warning, "
        "unhealthy, and 'unknown', which the storage stack reports on a "
        "perfectly healthy NVMe while OperationalStatus says ok - both are "
        "shown), the partition layout decoded from its GUID type (efi system, "
        "microsoft reserved, basic data, windows recovery) with each "
        "partition's size, offset and letter, the largest contiguous free "
        "extent, and for a volume the free-space verdict in words (under 5 "
        "percent critical, under 10 percent low, else fine) with the owning "
        "disk's health beside it. target matches a drive letter ('C:' or "
        "'C'), a volume label, a disk model, a serial number or a disk "
        "number ('0', 'disk 0'). Use it for 'is this drive about to fail' "
        "and 'what exactly lives on this disk'. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Which disk or volume: a drive letter ('C:' or 'C'), a "
                    "volume label ('Data'), a disk model ('UMIS'), a serial "
                    "number, or a disk number ('0', 'disk 0')."
                ),
            },
        },
        "required": ["target"],
    },
}
