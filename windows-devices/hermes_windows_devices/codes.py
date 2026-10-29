"""What a device's ConfigManagerErrorCode means, in words a person can act on."""

from __future__ import annotations

# the codes Device Manager's yellow mark stands behind; the everyday ones first
CODE_MEANINGS = {
    0: "working",
    1: "configured incorrectly",
    10: "cannot start",
    12: "not enough free resources for it",
    14: "needs a restart to finish",
    18: "its driver must be reinstalled",
    21: "Windows is removing it",
    22: "disabled (the person, or a policy, switched it off)",
    24: "not present or not working",
    28: "no driver is installed for it",
    31: "not working properly",
    37: "its driver failed to initialize",
    39: "its driver is missing or corrupt",
    43: "Windows stopped it after it reported a failure",
}

# codes that are an intentional state rather than a breakage
INTENTIONAL = {0, 22}


def code_of(value) -> dict | None:
    """A ConfigManagerErrorCode as a number and what it means."""
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return {"code": value, "meaning": None}
    return {"code": number, "meaning": CODE_MEANINGS.get(number, "no known meaning")}


def broken(code) -> bool:
    """Whether the code is a device that needs help (a disabled one does not)."""
    return isinstance(code, int) and code not in INTENTIONAL
