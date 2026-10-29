"""Tool schemas for the two device tools."""

DEVICE_TABLE = {
    "name": "win_device_table",
    "description": (
        "Answer 'which device on this Windows machine is unhappy' : lists every present "
        "PnP device with its class (System, Net, HIDClass, Display, ...), its status, its "
        "manufacturer, its device id, and its problem code in words -- 28 is one with no "
        "driver installed, 10 one that cannot start, 43 one Windows stopped after it "
        "reported a failure, 22 one the person switched off on purpose. Filter by name or "
        "id substring, by class, or to the devices that need attention. Use it for the "
        "Device Manager yellow-mark question without opening Device Manager, for finding "
        "what an uninstalled program left behind, and for 'what changed after that "
        "update'. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the device's name or its DeviceID, "
                    "e.g. 'camera', 'usb', 'LENOVO'."
                ),
            },
            "class": {
                "type": "string",
                "description": "Only devices in this PNPClass, e.g. 'Net', 'HIDClass', 'Display'.",
            },
            "broken_only": {
                "type": "boolean",
                "description": (
                    "Only devices that need attention (a disabled one does not; default "
                    "false)."
                ),
            },
            "include_absent": {
                "type": "boolean",
                "description": (
                    "Include historical devices that are not plugged in any more "
                    "(default false: only present ones)."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return, 1 to 300 (default 100).",
            },
        },
    },
}

DEVICE_DETAIL = {
    "name": "win_device_detail",
    "description": (
        "One device in full, for 'what is this thing and what does it need': everything "
        "the listing shows, plus the driver behind it -- its name, version, date, "
        "provider, signer, INF file, and whether it is signed -- or the absence of one, "
        "which for problem code 28 is the same fact said twice. Match by device id or by "
        "a name substring. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The device's name (a substring works) or its exact DeviceID; "
                    "win_device_table lists them all."
                ),
            },
        },
        "required": ["name"],
    },
}
