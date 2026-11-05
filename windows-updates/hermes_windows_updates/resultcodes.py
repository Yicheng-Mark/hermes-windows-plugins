"""What the update history's result codes mean, in words a person can act on."""

from __future__ import annotations

# what IUpdateHistoryEntry.ResultCode carries, fixed by the Windows Update Agent API and
# the same on every install language.
RESULT_MEANINGS = {
    1: "it is still in progress",
    2: "it succeeded",
    3: "it succeeded with errors",
    4: "it failed",
    5: "it was aborted",
}

# codes that describe an update that did not end clean
FAILED_RESULTS = {3, 4, 5}


def result_of(raw) -> dict | None:
    """A ResultCode as a number and what it means."""
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return {"code": raw, "meaning": None}
    return {
        "code": value,
        "meaning": RESULT_MEANINGS.get(value, "no known meaning"),
    }


def hresult_of(raw) -> dict | None:
    """An HResult as a number and its hex spelling.

    The Agent hands the value over as a signed 32-bit integer — a failed Defender
    signature update carries ``-2145124300`` — so the hex is masked to the unsigned
    ``0x`` form a person can paste into a search box.
    """
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return {"code": raw, "hex": None}
    return {
        "code": value,
        "hex": f"0x{value & 0xFFFFFFFF:08X}",
    }


def is_failed(result: dict | None) -> bool:
    """Whether a decoded result is one of the not-clean endings."""
    if not isinstance(result, dict):
        return False
    try:
        return int(result.get("code")) in FAILED_RESULTS
    except (TypeError, ValueError):
        return False
