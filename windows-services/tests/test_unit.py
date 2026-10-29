"""Unit tests: every layer with fakes, no PowerShell, no registry, no disk."""

from __future__ import annotations

import json
import struct

import pytest

from hermes_windows_services import exitcodes, svcreg, tools


# every registry-reading test gets the fake QueryValueEx; openers are injected per call
@pytest.fixture(autouse=True)
def _fake_query(monkeypatch):
    monkeypatch.setattr(svcreg.winreg, "QueryValueEx", _read)


# --- exit codes and event words -------------------------------------------

def test_exit_code_words_and_never_started_is_not_a_failure():
    never = exitcodes.exit_of(1077)
    assert never["meaning"] == "it has not tried to start since the last boot"
    assert never["hex"] == "0x00000435"
    assert 1077 in exitcodes.NOT_A_FAILURE and 0 in exitcodes.NOT_A_FAILURE
    assert 1067 not in exitcodes.NOT_A_FAILURE
    assert exitcodes.exit_of(None) is None
    assert exitcodes.exit_of("junk") == {"code": "junk", "hex": None, "meaning": None}


def test_scm_event_words():
    assert "timed out" in exitcodes.sc_event_of(7009)
    assert "installed" in exitcodes.sc_event_of(7045)
    assert "7036" not in exitcodes.sc_event_of(7036)  # routine noise: not translated, not collected


# --- the FailureActions blob ----------------------------------------------

def _blob(actions: list[tuple[int, int]], reset: int = 86400) -> bytes:
    head = struct.pack("<5I", reset, 0, 0, len(actions), 20)
    return head + b"".join(struct.pack("<2I", kind, delay) for kind, delay in actions)


def test_failure_policy_reads_wuauserv_shape():
    policy = svcreg.failure_policy("wuauserv", opener=_opener_with(
        {"wuauserv": {"FailureActions": _blob([(1, 60000), (1, 60000), (1, 60000)])}}))
    assert policy["count"] == 3
    assert policy["reset_after_hours"] == 24.0
    assert policy["actions"] == [
        {"type": "restart the service", "after_seconds": 60.0},
        {"type": "restart the service", "after_seconds": 60.0},
        {"type": "restart the service", "after_seconds": 60.0},
    ]


def test_failure_policy_without_actions_is_none_or_empty():
    assert svcreg.failure_policy("plain", opener=_opener_with({})) is None
    empty = svcreg.failure_policy("empty", opener=_opener_with(
        {"empty": {"FailureActions": _blob([])}}))
    assert empty["actions"] == []


# --- the registry layer, faked --------------------------------------------

class _FakeKey:
    def __init__(self, values):
        self._values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener_with(table):
    """A winreg.OpenKey stand-in answering from {service: {value_name: value}}."""

    def open_key(root, path):
        name = path.rsplit("\\", 1)[-1]
        if name in table:
            return _FakeKey(table[name])
        raise OSError("not found")

    return open_key


def _read(key, value_name):  # noqa: ANN001 - mirrors winreg.QueryValueEx's (value, type) pair
    try:
        return key._values[value_name], 0
    except KeyError:
        raise FileNotFoundError(value_name)  # what QueryValueEx raises for an unset value


def test_depends_on_reads_group_prefixes(monkeypatch):
    monkeypatch.setattr(svcreg.winreg, "QueryValueEx", _read)
    table = {"dns": {"DependOnService": ["nsi", "Afd", "+TDI"]}}
    got = svcreg.depends_on("dns", opener=_opener_with(table))
    assert got == ["nsi", "Afd", "TDI (group)"]
    assert svcreg.depends_on("gone", opener=_opener_with(table)) == []


def test_delayed_start_flag(monkeypatch):
    monkeypatch.setattr(svcreg.winreg, "QueryValueEx", _read)
    table = {"bits": {"DelayedAutostart": 1}, "plain": {}}
    assert svcreg.delayed_start("bits", opener=_opener_with(table)) is True
    assert svcreg.delayed_start("plain", opener=_opener_with(table)) is False


# --- the tools, with the CIM and registry both faked ----------------------

CIM = [
    {"name": "wuauserv", "display": "Windows Update", "state": "Stopped", "start": "Auto",
     "delayed": False, "pid": 0, "exit_code": 0, "account": "LocalSystem",
     "binary": r"C:\Windows\system32\svchost.exe -k netsvcs", "description": "Updates"},
    {"name": "broken", "display": "Broken Thing", "state": "Stopped", "start": "Auto",
     "delayed": False, "pid": 0, "exit_code": 2, "account": "LocalSystem",
     "binary": r"C:\Program Files\Gone\thing.exe", "description": None},
    {"name": "dns", "display": "DNS Client", "state": "Running", "start": "Manual",
     "delayed": False, "pid": 1234, "exit_code": 0, "account": "LocalService",
     "binary": r"C:\Windows\system32\svchost.exe -k NetworkService", "description": None},
    {"name": "bits", "display": "BITS", "state": "Running", "start": "Auto",
     "delayed": True, "pid": 0, "exit_code": 0, "account": "LocalSystem",
     "binary": r"C:\Windows\system32\svchost.exe", "description": None},
]

REG = {
    "wuauserv": {"DependOnService": ["rpcss"], "DelayedAutostart": 1},
    "broken": {"FailureActions": _blob([(1, 5000)])},
    "dns": {"DependOnService": ["nsi", "+TDI"]},
}


@pytest.fixture()
def faked(monkeypatch):
    monkeypatch.setattr(tools.svcquery, "services", lambda: [dict(item) for item in CIM])
    # the registry runs its real code (group prefixes, blob parsing) over the fake opener,
    # so the tools exercise svcreg itself rather than a copy of its answers
    real_depends, real_delayed, real_policy = (
        svcreg.depends_on, svcreg.delayed_start, svcreg.failure_policy)
    monkeypatch.setattr(tools.svcreg, "depends_on",
                        lambda name, opener=None: real_depends(name, _opener_with(REG)))
    monkeypatch.setattr(tools.svcreg, "delayed_start",
                        lambda name, opener=None: real_delayed(name, _opener_with(REG)))
    monkeypatch.setattr(tools.svcreg, "failure_policy",
                        lambda name, opener=None: real_policy(name, _opener_with(REG)))
    monkeypatch.setattr(tools.svcquery, "failures", lambda name: [
        {"time": "2026-10-28T08:00:00", "id": 7024, "what": "Broken Thing ended with a service-specific error"}
    ] if name == "broken" else [])


def _load(text: str) -> dict:
    return json.loads(text)


def test_table_lists_filters_and_reverse_dependencies(faked):
    answer = _load(tools.win_service_table({}))
    assert answer["ok"] is True
    names = [row["name"] for row in answer["services"]]
    assert set(names) >= {"wuauserv", "broken", "dns", "bits"}
    dns = next(row for row in answer["services"] if row["name"] == "dns")
    assert dns["depends_on"] == ["nsi", "TDI (group)"]
    rpcss_side = next(row for row in answer["services"] if row["name"] == "wuauserv")
    # the delayed flag from the registry folds into the start mode
    assert rpcss_side["start"] == "Auto, delayed"

    by_name = {row["name"]: row for row in answer["services"]}
    assert by_name["bits"]["start"] == "Auto, delayed"  # CIM's own flag, registry absent

    only_failed = _load(tools.win_service_table({"nonzero_exit": True}))
    assert [row["name"] for row in only_failed["services"]] == ["broken"]
    assert any("non-zero exit code" in note for note in only_failed["notes"])

    started = _load(tools.win_service_table({"state": "running"}))
    assert {row["name"] for row in started["services"]} == {"dns", "bits"}

    narrow = _load(tools.win_service_table({"query": "update"}))
    assert [row["name"] for row in narrow["services"]] == ["wuauserv"]


def test_table_limit_and_notes(faked):
    answer = _load(tools.win_service_table({"limit": 2}))
    assert len(answer["services"]) == 2
    assert any("stopped at limit" in note for note in answer["notes"])
    nothing = _load(tools.win_service_table({"query": "nothing-matches"}))
    assert nothing["services"] == [] and any("nothing matched" in n for n in nothing["notes"])
    bad_state = _load(tools.win_service_table({"state": "sideways"}))
    assert any("state is one of" in note for note in bad_state["notes"])


def test_detail_reads_one_service_in_full(faked):
    answer = _load(tools.win_service_detail({"name": "broken"}))
    assert answer["ok"] is True
    assert answer["exit_code"]["meaning"] == "the binary could not be found"
    assert answer["failure_policy"]["actions"][0]["after_seconds"] == 5.0
    assert answer["binary"]["present"] is False
    assert any("not on disk" in note for note in answer["notes"])
    assert answer["recent_failures"][0]["what_happened"] == "ended with a service-specific error"
    assert answer["recent_failures"][0]["event_id"] == 7024


def test_detail_names_and_suggests(faked):
    missing = _load(tools.win_service_detail({"name": "wuaus"}))
    assert missing["ok"] is False
    assert missing["code"] == "not_registered"
    assert "wuauserv" in missing["suggestions"]
    no_name = _load(tools.win_service_detail({}))
    assert no_name["code"] == "name_required"


def test_detail_notes_when_no_failure_action_is_configured(faked):
    answer = _load(tools.win_service_detail({"name": "dns"}))
    assert answer["failure_policy"] is None
    assert any("no failure action" in note for note in answer["notes"])


def test_table_survives_a_dead_registry(monkeypatch):
    monkeypatch.setattr(tools.svcquery, "services", lambda: [dict(item) for item in CIM])
    monkeypatch.setattr(tools.svcreg, "depends_on",
                        lambda name, opener=None: (_ for _ in ()).throw(svcreg.RegistryUnavailable("no")))
    answer = _load(tools.win_service_table({}))
    assert answer["ok"] is True
    assert all(row["depends_on"] == [] for row in answer["services"])
