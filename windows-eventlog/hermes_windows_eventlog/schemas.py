"""Tool schemas — the descriptions the model reads before choosing a tool."""

CRASH_EVENTS = {
    "name": "win_crash_events",
    "description": (
        "Read Windows crash evidence for a time window and explain why a process died: "
        "Application Error / Application Hang / Windows Error Reporting / .NET Runtime "
        "records from the Application event log, with the faulting module and a decoded "
        "exception code (e.g. 0xC0000005 ACCESS_VIOLATION). Returns the individual records "
        "plus groups that collapse repeated crashes of the same app and signature. Use this "
        "when a program, the Hermes desktop app, the gateway or a backend vanished, hung, or "
        "was reported as 'crashed' — on Windows the Application log is the only durable "
        "record of the faulting module and offset. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "number",
                "description": "How far back to look, in hours (default 24, max 720).",
            },
            "process": {
                "type": "string",
                "description": (
                    "Optional case-insensitive filter, matched against the crashing image "
                    "name and path (e.g. 'hermes', 'python.exe', 'codex')."
                ),
            },
            "kinds": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["application_error", "application_hang", "wer", "dotnet"],
                },
                "description": "Limit to specific record kinds. Omit for all of them.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum records to return (default 25, max 200).",
            },
        },
        "required": [],
    },
}

SHUTDOWN_EVENTS = {
    "name": "win_shutdown_events",
    "description": (
        "Read the System event log for machine-level interruptions: Kernel-Power 41 "
        "unexpected restarts, bugchecks (Event 1001 from WER-SystemErrorReporting, decoded "
        "to names like DRIVER_POWER_STATE_FAILURE), EventLog 6008 dirty shutdowns, 1074 "
        "operator-initiated restarts with the process and reason, and the 6005/6006/12/13 "
        "start/stop markers. Use this when Hermes or its gateway died together with the "
        "machine, after sleep/hibernate, or when sessions stop without an exit record. "
        "Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "number",
                "description": "How far back to look, in hours (default 168 = one week, max 720).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum records to return (default 30, max 200).",
            },
        },
        "required": [],
    },
}

EVENTLOG_QUERY = {
    "name": "win_eventlog_query",
    "description": (
        "Query any Windows event log channel with filters (event ids, levels, exact "
        "provider name, substring) and get structured records instead of raw XML. Use it "
        "for everything the two crash tools do not cover: Service Control Manager 7031/7034 "
        "service crashes, Task Scheduler, Kernel-Power, application-specific Operational "
        "logs, or 'find the event that mentions this path/port/error'. Read-only; Windows "
        "only; channels that require elevation (e.g. Security) return an access-denied error."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": (
                    "Log name, e.g. 'Application' (default), 'System', or "
                    "'Microsoft-Windows-TaskScheduler/Operational'."
                ),
            },
            "hours": {
                "type": "number",
                "description": "How far back to look, in hours (default 24, max 720).",
            },
            "event_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Only these event ids (e.g. [7031, 7034]).",
            },
            "levels": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 5},
                "description": "Only these levels: 1 critical, 2 error, 3 warning, 4 information, 5 verbose.",
            },
            "provider": {
                "type": "string",
                "description": "Exact provider name, e.g. 'Service Control Manager'.",
            },
            "contains": {
                "type": "string",
                "description": "Case-insensitive substring the event payload must contain.",
            },
            "include_details": {
                "type": "boolean",
                "description": "Include the provider's named data fields (default false).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum records to return (default 20, max 200).",
            },
        },
        "required": [],
    },
}
