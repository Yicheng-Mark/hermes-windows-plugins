"""Tool schemas for the two certificate tools."""

CERT_TABLE = {
    "name": "win_cert_table",
    "description": (
        "Answer 'which certificate on this machine is expired or about to be, and "
        "where does it live': walks the Windows certificate stores (the current "
        "user's and the machine's MY, Root and CA) and lists every certificate with "
        "its subject, issuer, validity window, whether it is self-signed, its "
        "SHA-1 thumbprint and the store it lives in. The expiry arrives in words — "
        "'expired 45 days ago', 'expires in 12 days' — and the list is sorted with "
        "the expired and soon-expiring ones first. Filter to the user's or the "
        "machine's copies, to one store, to certificates that are expired or "
        "expiring within 30 days, or by a subject substring such as a CA or a "
        "hostname. Use it for 'why does TLS keep failing on this box', 'is the "
        "root store healthy', and 'which personal certificate ran out'. "
        "Read-only: the stores are opened read-only and only enumerated - "
        "nothing is added, removed or changed, and no network call is made. "
        "Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "context": {
                "type": "string",
                "description": (
                    "Whose copies to walk: 'user' (the current user's stores), "
                    "'machine' (the local machine's), or 'both' (default)."
                ),
            },
            "store": {
                "type": "string",
                "description": (
                    "One store only, by name: 'MY' (personal), 'Root' (trusted "
                    "roots), or 'CA' (intermediate CAs). Default: all three."
                ),
            },
            "expired_only": {
                "type": "boolean",
                "description": (
                    "Only certificates that are expired or expire within 30 days "
                    "(default false)."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the subject, the issuer or the "
                    "friendly name, e.g. 'DigiCert', 'localhost', 'Contoso'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return, 1 to 400 (default 100).",
            },
        },
    },
}

CERT_DETAIL = {
    "name": "win_cert_detail",
    "description": (
        "One certificate in full, from the Windows certificate stores: subject, "
        "issuer, friendly name, serial number, certificate version, SHA-1 "
        "thumbprint, the signature algorithm in words (sha256WithRSAEncryption, "
        "ecdsaWithSHA256...), the public key's algorithm, named curve and size in "
        "bits (a 2048-bit RSA key, a P-256 curve), the purposes it is valid for "
        "(server authentication, code signing...; a certificate with no EKU "
        "extension is reported as valid for any purpose, which is what the "
        "extension's absence means), self-signed or not, and the validity window "
        "with the expiry in words - 'expired 45 days ago', 'expires in 12 days'. "
        "Find it by thumbprint (exact) or by a subject/issuer substring; when "
        "several match, the candidates are listed so a thumbprint can pick one "
        "out. Read-only, in-process, no network. Windows only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "thumbprint": {
                "type": "string",
                "description": (
                    "The SHA-1 thumbprint as hex (spaces and colons ignored, case "
                    "does not matter) - the exact certificate."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive substring of the subject, issuer or friendly "
                    "name, when no thumbprint is given."
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "'user', 'machine' or 'both' (default), to narrow the search."
                ),
            },
            "store": {
                "type": "string",
                "description": "One store only: 'MY', 'Root' or 'CA'.",
            },
        },
    },
}
