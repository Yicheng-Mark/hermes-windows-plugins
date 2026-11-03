"""Tool schemas for the two startup tools."""

STARTUP_TABLE = {
    "name": "win_startup_table",
    "description": (
        "Answer 'what launches itself on this Windows machine' : every autostart entry "
        "across the six Run/RunOnce registry keys (HKCU, HKLM, and the 32-bit views) and "
        "the two Startup folders, with where each one comes from, whether it is machine- "
        "or user-scoped, and whether the person switched it off in Task Manager (the "
        "StartupApproved verdict, with when it was last changed) -- a state Task "
        "Manager's own list shows but Win32_StartupCommand does not. Also reports "
        "approval records left behind by uninstalled programs. Use it for 'what added "
        "itself since last month', for slimming a slow sign-in, and for spotting a "
        "launcher whose binary is gone. Read-only; nothing is enabled, disabled or "
        "deleted. Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the entry's name or its command, "
                    "e.g. 'onedrive', 'securityhealth', 'cc switch'."
                ),
            },
            "scope": {
                "type": "string",
                "description": "Only 'user' or only 'machine' entries.",
            },
            "include_disabled": {
                "type": "boolean",
                "description": "Include entries switched off in Task Manager (default true).",
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return, 1 to 400 (default 100).",
            },
        },
    },
}

STARTUP_DETAIL = {
    "name": "win_startup_detail",
    "description": (
        "One autostart entry in full: the exact command it launches, the binary that "
        "command resolves to (quoting, arguments and environment variables included) and "
        "whether that binary is still on disk, the folder file's size and last change "
        "when it lives in a Startup folder, and Explorer's enabled/disabled verdict with "
        "when the person last changed it. Use it after win_startup_table names a "
        "suspect. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The entry's registered name as win_startup_table showed it, e.g. "
                    "'SecurityHealth' or 'CC Switch' (case-insensitive)."
                ),
            },
        },
        "required": ["name"],
    },
}
