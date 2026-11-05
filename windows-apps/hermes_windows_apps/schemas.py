"""Tool schemas for the two installed-software tools."""

APP_TABLE = {
    "name": "win_app_table",
    "description": (
        "Answer 'what is installed on this Windows machine' : the software "
        "inventory behind Apps & Features, swept straight from the four "
        "Uninstall registry keys (the machine's 64-bit and 32-bit views plus "
        "the user's), so a program is found even when the Settings page hides "
        "it. Each row carries version, publisher, size, install date and which "
        "view it lives in -- the same DisplayName in two views is a 32/64-bit "
        "dual install, marked instead of listed twice. Entries the publisher "
        "asked to hide (runtime packages, update rollups: SystemComponent) are "
        "filtered out unless asked for. Use it for 'is X installed, which "
        "version', for finding disk-heavy software, and for inventory before a "
        "cleanup. Read-only; uninstall commands are reported, never run. "
        "Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the program's name or its "
                    "publisher, e.g. 'visual c++', 'python', 'obs'."
                ),
            },
            "view": {
                "type": "string",
                "description": "Only one view: machine-64, machine-32, user-64 or user-32.",
            },
            "include_system_components": {
                "type": "boolean",
                "description": (
                    "Include entries hidden from Apps & Features (runtimes, "
                    "updates; default false)."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return, 1 to 400 (default 100).",
            },
        },
    },
}

APP_DETAIL = {
    "name": "win_app_detail",
    "description": (
        "One installed program in full: every field its publisher wrote -- "
        "version, publisher, size, install date, install location and whether "
        "that folder still exists, help and about links, comments -- plus a "
        "reading of the uninstall command (MSI database GUID, setup "
        "executable, or script), so the next step is known before anything is "
        "run. A program present in several registry views is shown once with "
        "all its occurrences (the 32/64-bit dual install case). Use it after "
        "win_app_table names a program. Read-only; the uninstall string is "
        "classified and quoted, never executed. Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The program's DisplayName as win_app_table showed it, "
                    "e.g. 'Python 3.13' or 'OBS Studio' (case-insensitive)."
                ),
            },
        },
        "required": ["name"],
    },
}
