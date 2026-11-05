"""Tool schemas for the two adapter tools."""

ADAPTER_TABLE = {
    "name": "win_adapter_table",
    "description": (
        "Answer 'is this machine's network healthy, and which adapter is the problem' on "
        "Windows: lists every visible network adapter with its state (up, disconnected, "
        "disabled, not present), its link speed as a number, its MAC, whether it is virtual "
        "(Hyper-V, VPN, virtual switch), and its driver version and date. Physical adapters "
        "are separated from virtual ones, and adapters whose hardware is not present are "
        "left out unless asked for. Use it for 'why is there no internet', for telling a "
        "cable that is unplugged from an adapter that was switched off, and for finding "
        "which of several adapters the machine actually uses. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the adapter's name or its description, "
                    "e.g. 'wlan', 'ethernet', 'wi-fi', 'hyper-v', 'vpn'."
                ),
            },
            "state": {
                "type": "string",
                "enum": ["up", "disconnected", "disabled", "not present", "testing"],
                "description": "Only adapters in this state.",
            },
            "virtual": {
                "type": "boolean",
                "description": (
                    "true shows only virtual adapters (Hyper-V, VPN, virtual switch), "
                    "false only physical ones; leave it out for both."
                ),
            },
            "include_absent": {
                "type": "boolean",
                "description": (
                    "Include adapters whose hardware is not present -- ghosts of radios "
                    "and slots that are gone (default false)."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "How many adapters to list (default 50, at most 200).",
            },
        },
    },
}

ADAPTER_DETAIL = {
    "name": "win_adapter_detail",
    "description": (
        "One Windows network adapter in full: its IPv4 and IPv6 addresses with their "
        "prefixes and where each came from (DHCP, manual, self-assigned), its default "
        "gateways, its DNS servers, its driver, and a diagnosis in plain words -- a "
        "169.254.x.x address means DHCP never answered, an address without a gateway "
        "cannot leave its own subnet, an adapter with no DNS servers cannot resolve "
        "names, and a healthy adapter has all three. Use it after win_adapter_table "
        "named the adapter whose connectivity is in question. Read-only; Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The adapter's name or a substring of its description, as "
                    "win_adapter_table prints it, e.g. 'WLAN', '以太网' or 'vEthernet'."
                ),
            },
        },
        "required": ["name"],
    },
}

__all__ = ["ADAPTER_DETAIL", "ADAPTER_TABLE"]
