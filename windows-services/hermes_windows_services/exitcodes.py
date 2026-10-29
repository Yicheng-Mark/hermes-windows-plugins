"""What a service's exit code and the SCM event log mean, in words a person can act on."""

from __future__ import annotations

# what Win32_Service's ExitCode carries after the SCM last tried to run the service.
# Values are Win32 error numbers, not HRESULTs; the common ones a broken service leaves.
EXIT_MEANINGS = {
    0: "success",
    2: "the binary could not be found",
    3: "the binary's path could not be found",
    5: "access was denied",
    14: "not enough storage to run it",
    193: "the binary is not a valid Win32 program",
    126: "a DLL it needs could not be found",
    1053: "it did not answer the start request in time",
    1055: "the account it runs as could not log on",
    1056: "an instance was already running",
    1058: "it is disabled and cannot be started",
    1062: "it has not been started",
    1067: "the process ended unexpectedly",
    1072: "it is marked for deletion",
    1075: "a service it depends on failed to start first",
    1077: "it has not tried to start since the last boot",
}

# exit codes that describe an untouched service rather than a failure
NOT_A_FAILURE = {0, 1077}

# the Service Control Manager's own event ids, System channel. 7036 (state changed) and
# 7040 (start type changed) are routine noise and deliberately not collected.
SCM_EVENT_MEANINGS = {
    7000: "failed to start",
    7001: "could not connect to the service controller as its account",
    7009: "a start request timed out (30 s)",
    7011: "a control request timed out",
    7023: "ended with an error",
    7024: "ended with a service-specific error",
    7031: "ended unexpectedly",
    7034: "ended unexpectedly, more than once inside a minute",
    7045: "was installed on this machine",
}


def exit_of(code) -> dict | None:
    """An ExitCode as a number, its hex and what it means."""
    if code is None:
        return None
    try:
        value = int(code)
    except (TypeError, ValueError):
        return {"code": code, "hex": None, "meaning": None}
    return {
        "code": value,
        "hex": f"0x{value & 0xFFFFFFFF:08X}",
        "meaning": EXIT_MEANINGS.get(value & 0xFFFFFFFF, "no known meaning"),
    }


def sc_event_of(event_id) -> str:
    """What an SCM event id means, in a few words."""
    try:
        key = int(event_id)
    except (TypeError, ValueError):
        return "unknown event"
    return SCM_EVENT_MEANINGS.get(key, "an event this tool does not translate")
