"""Tool schemas for the two scheduled-task tools."""

SCHEDULED_TASKS = {
    "name": "win_scheduled_tasks",
    "description": (
        "Answer 'what does this machine run on its own, and did it work' on Windows: lists "
        "the Task Scheduler's tasks with their state (Ready, Running, Disabled), the account "
        "each runs as, its first action's command line, its triggers in words (at logon, "
        "daily, weekly, at a time, on event), its last and next run with the machine's "
        "offset, how many runs it missed, and what its last result code means -- 0x80070002 "
        "is a program that is no longer there, 0x800710E0 a task that needed a desktop it "
        "did not have, 0x40010004 one that was stopped. Filter by path substring, by state, "
        "or to the tasks whose last run failed. Use it for 'why does this keep failing', "
        "for finding what an uninstalled program left behind at logon, and for telling a "
        "disabled task from a broken one. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the task's path, e.g. 'wps', 'update', "
                    "'hermes'."
                ),
            },
            "state": {
                "type": "string",
                "enum": ["ready", "running", "disabled", "queued", "unknown"],
                "description": "Only tasks in this state.",
            },
            "failed_only": {
                "type": "boolean",
                "description": (
                    "Only tasks whose last run ended with a failure (a task that has never "
                    "run is not a failure; default false)."
                ),
            },
            "include_microsoft": {
                "type": "boolean",
                "description": (
                    "Include Windows' own tasks, the ones under \\Microsoft\\... "
                    "(default false)."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "description": "How many tasks to list (default 100, at most 500).",
            },
        },
    },
}

SCHEDULED_TASK_DETAIL = {
    "name": "win_scheduled_task_detail",
    "description": (
        "One Windows scheduled task in full: every trigger with its start boundary, "
        "repetition and schedule, every action with its arguments and working directory, "
        "the principal it runs as, and the settings that decide whether it runs on battery "
        "or when late, alongside its state and last and next run. A task with no triggers "
        "but MaintenanceSettings runs during automatic maintenance, and the notes say so. "
        "Use it after win_scheduled_tasks named the task whose command line or schedule you "
        "need to see. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The task's full path as win_scheduled_tasks prints it, e.g. "
                    "'\\\\Hermes_Gateway' or "
                    "'\\\\Microsoft\\\\Windows\\\\Defrag\\\\ScheduledDefrag'. A leading "
                    "backslash is optional."
                ),
            },
        },
        "required": ["name"],
    },
}

__all__ = ["SCHEDULED_TASK_DETAIL", "SCHEDULED_TASKS"]
