"""Tool schemas for the two service tools."""

SERVICE_TABLE = {
    "name": "win_service_table",
    "description": (
        "Answer 'what runs as a service on this Windows machine, and did it work' : lists "
        "every service with its state (Running, Stopped, Paused), its start mode (Auto, "
        "Manual, Disabled, and the delayed flag folded in the way Services shows it), the "
        "pid it runs under or null when it is not running, the account and binary it runs "
        "as, the services it waits for and the ones that wait for it, and what its exit "
        "code means -- 1077 is one that has not tried to start since the last boot, 1053 "
        "one that did not answer in time, 1075 one whose dependency failed first, 2 one "
        "whose binary is gone. Filter by name or display substring, by state, by start "
        "mode, or to the services carrying a non-zero exit code. Use it for 'what died "
        "after the last update', for finding what an uninstalled program left registered, "
        "and for the dependency order before a restart. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the service's name or display name, "
                    "e.g. 'wuauserv', 'update', 'hermes'."
                ),
            },
            "state": {
                "type": "string",
                "enum": [
                    "running", "stopped", "paused", "start pending", "stop pending",
                    "continue pending", "pause pending", "unknown",
                ],
                "description": "Only services in this state.",
            },
            "start": {
                "type": "string",
                "enum": ["boot", "system", "auto", "manual", "disabled"],
                "description": (
                    "Only services with this start mode; a delayed Automatic service "
                    "matches start=auto."
                ),
            },
            "nonzero_exit": {
                "type": "boolean",
                "description": (
                    "Only services whose exit code is a failure (1077, never started, is "
                    "not one; default false)."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return, 1 to 400 (default 100).",
            },
        },
    },
}

SERVICE_DETAIL = {
    "name": "win_service_detail",
    "description": (
        "One service in full, for 'why is this one not running': everything the listing "
        "shows, plus what Windows does when it fails (restart the service, restart the "
        "computer, run a command, after how many seconds, and when it forgets the count), "
        "whether the registered binary is still on disk, and the Service Control Manager's "
        "own event-log record behind the failure -- 7000 failed to start, 7009 a start "
        "request timed out, 7024 ended with a service-specific error, 7031 ended "
        "unexpectedly, 7045 was installed. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The service's name (not its display name), e.g. 'wuauserv'; "
                    "win_service_table lists them all."
                ),
            },
        },
        "required": ["name"],
    },
}
