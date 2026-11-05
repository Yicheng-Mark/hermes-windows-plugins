"""Tool schemas for the two update tools."""

UPDATE_HISTORY = {
    "name": "win_update_history",
    "description": (
        "Answer 'what did Windows install lately, and did it work': the update history "
        "the Settings app shows — Windows updates, Defender signature and platform "
        "updates, driver updates — newest first, each with its outcome in words (2 "
        "succeeded, 3 succeeded with errors, 4 failed, 5 aborted, 1 still in progress) "
        "and, when it did not end clean, the failure's error code in the 0x form a "
        "person can paste into a search box (the Agent hands them over signed; "
        "-2145124300 is shown as its unsigned spelling). Filter to the ones that did "
        "not end clean, or by a title substring such as 'Defender' or a KB number. Use "
        "it for 'why is this machine stuck on an old build', 'did the driver update "
        "actually install', and 'what kept failing last week'. Read-only: the history "
        "is only queried, nothing is searched for, downloaded, installed or "
        "uninstalled. Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": (
                    "Newest entries to consider, 1 to 500 (default 50). A machine with "
                    "signature updates enabled can carry hundreds per month."
                ),
            },
            "only_failures": {
                "type": "boolean",
                "description": (
                    "Only entries whose outcome is not clean: failed, aborted, or "
                    "succeeded with errors (default false)."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the entry's title, e.g. "
                    "'Defender', 'KB2267602', 'driver'."
                ),
            },
        },
    },
}

HOTFIX_TABLE = {
    "name": "win_hotfix_table",
    "description": (
        "The OS-level hotfix list — KB numbers, security updates, when each was "
        "installed and by whom — for 'when was this machine last patched' at a glance. "
        "The quick-fix list carries only OS-level updates; apps, Defender signatures "
        "and drivers are not in it, and win_update_history answers those in full. "
        "Sorted newest install date first. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the KB id, e.g. '5127694' or 'KB50'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return, 1 to 400 (default 100).",
            },
        },
    },
}
