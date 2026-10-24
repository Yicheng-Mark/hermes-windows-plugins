"""Tool schema for the port-owner tool."""

PORT_OWNERS = {
    "name": "win_port_owners",
    "description": (
        "Answer 'who holds this port' on Windows: lists local TCP/UDP endpoints from the "
        "same table netstat -ano prints, with the owning PID and image name attached, so "
        "no console parsing is needed. Filter by port, by process, by protocol and by state "
        "(listen / established / all). Use it for bind failures and EADDRINUSE-style errors, "
        "for 'is something already listening on 3000', for finding a stale gateway or "
        "backend holding a port, and for seeing which process owns an established "
        "connection. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "minimum": 0,
                "maximum": 65535,
                "description": "A single local port to match.",
            },
            "ports": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 65535},
                "description": "Several local ports to match (combined with port).",
            },
            "process": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the image name or path, "
                    "e.g. 'hermes', 'node', 'python'."
                ),
            },
            "protocol": {
                "type": "string",
                "enum": ["tcp", "udp", "both"],
                "description": "Which tables to read (default both).",
            },
            "state": {
                "type": "string",
                "description": (
                    "TCP state filter: 'listen' for servers, 'established' for live "
                    "connections, 'all' (default) for everything. UDP rows report 'bound'."
                ),
            },
            "include_ipv6": {
                "type": "boolean",
                "description": "Include the IPv6 tables (default true).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum endpoints to return (default 100, max 500).",
            },
        },
        "required": [],
    },
}
