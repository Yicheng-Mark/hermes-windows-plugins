"""Tool schema for the process-table tool."""

PROCESS_TABLE = {
    "name": "win_process_table",
    "description": (
        "Answer 'what is still running, and who started it' on Windows: reads the same "
        "process rows Task Manager prints (PID, parent PID, image name) and adds each "
        "process's image path and start time, then flags the ones whose parent is gone or "
        "whose parent PID was reused by a newer process -- the signature of a process that "
        "outlived the session that spawned it. Filter by pid, by process name, or by parent; "
        "ask for a pid's ancestor chain; or list only the orphans. Use it for leftover "
        "gateway/backend/server children after a quit, for 'which of these 30 python.exe is "
        "the live one', and for checking whether a long-lived process started before or "
        "after the thing you are debugging. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "minimum": 0,
                "description": "A single process ID to match.",
            },
            "pids": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0},
                "description": "Several process IDs to match (combined with pid).",
            },
            "process": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the image name or path, "
                    "e.g. 'hermes', 'python', 'node'."
                ),
            },
            "parent": {
                "type": "integer",
                "minimum": 0,
                "description": "Only processes whose parent PID is this value.",
            },
            "orphans_only": {
                "type": "boolean",
                "description": (
                    "Only processes whose parent is gone, or whose parent PID now belongs "
                    "to a process that started later than they did (default false)."
                ),
            },
            "with_ancestry": {
                "type": "boolean",
                "description": (
                    "Also return the ancestor chain of each matched PID, marked as context "
                    "rows (default false)."
                ),
            },
            "include_system": {
                "type": "boolean",
                "description": (
                    "Include Windows session and bootstrap processes (images under the "
                    "Windows directory) plus processes the account cannot open, which come "
                    "back without a path or start time (default true)."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum processes to return (default 100, max 500).",
            },
        },
        "required": [],
    },
}
