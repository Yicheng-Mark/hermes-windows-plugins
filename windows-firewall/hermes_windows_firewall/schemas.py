"""Tool schemas for the two firewall tools."""

FIREWALL_TABLE = {
    "name": "win_firewall_table",
    "description": (
        "Answer 'what does the Windows firewall let through, and for whom' : "
        "every firewall rule from the registry store the firewall service "
        "itself keeps, each row in plain words -- allow or block, inbound or "
        "outbound, TCP/UDP/ICMP or a protocol number, local and remote ports, "
        "the program or service the rule is scoped to, which profile it "
        "belongs to (Domain, Private, Public or any) and whether it is "
        "switched on -- plus the three profiles' firewall switches and "
        "default actions. Built-in rules name themselves indirectly; the "
        "words are resolved from the resource in the machine's own language, "
        "third-party rules read as written. Use it for 'is port X open', for "
        "'what may this exe do', and for 'is the firewall actually on'. "
        "Read-only; nothing is enabled, disabled, added or removed. "
        "Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "description": "Only one direction: in or out.",
            },
            "profile": {
                "type": "string",
                "description": (
                    "Only rules of this profile: domain, private, public or "
                    "any (rules written for all profiles)."
                ),
            },
            "active": {
                "type": "boolean",
                "description": (
                    "true lists only switched-on rules, false only switched-off "
                    "ones; unset lists both."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the rule's name, its id, "
                    "its program or its service, e.g. 'svchost', 'NETDIS', "
                    "'python'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return, 1 to 400 (default 100).",
            },
        },
    },
}

FIREWALL_DETAIL = {
    "name": "win_firewall_detail",
    "description": (
        "One firewall rule in full: the sentence of what it does, its action "
        "and direction, protocol, local and remote ports, local and remote "
        "addresses with scope words (the local subnet, any address), edge "
        "traversal, the program and the service behind it, the group it "
        "belongs to, its description in the machine's language, and every "
        "field the parser does not model passed through verbatim rather than "
        "dropped. A switched-off rule says so: it matches nothing. Use it "
        "after win_firewall_table names a rule. Read-only. Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The rule's id as win_firewall_table showed it "
                    "(e.g. 'NETDIS-SSDPSrv-Out-UDP-Active') or any part of "
                    "its name (case-insensitive)."
                ),
            },
        },
        "required": ["name"],
    },
}
