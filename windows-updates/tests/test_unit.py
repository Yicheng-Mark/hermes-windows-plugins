"""Unit tests: every layer with fakes, no PowerShell, no COM, no CIM."""

from __future__ import annotations

import json

import pytest

from hermes_windows_updates import resultcodes, tools, wuquery


# --- the result-code and hresult words -------------------------------------

def test_result_code_words():
    assert resultcodes.result_of(2)["meaning"] == "it succeeded"
    assert resultcodes.result_of(4)["meaning"] == "it failed"
    assert resultcodes.result_of(5)["meaning"] == "it was aborted"
    assert resultcodes.result_of(3)["meaning"] == "it succeeded with errors"
    assert resultcodes.result_of(1)["meaning"] == "it is still in progress"
    assert resultcodes.result_of(99)["meaning"] == "no known meaning"
    assert resultcodes.result_of(None) is None
    assert resultcodes.result_of("junk") == {"code": "junk", "meaning": None}


def test_hresult_is_masked_to_the_unsigned_spelling():
    # the Agent hands codes over signed; a failed Defender update carries this one
    assert resultcodes.hresult_of(-2145124300) == {
        "code": -2145124300,
        "hex": f"0x{-2145124300 & 0xFFFFFFFF:08X}",
    }
    assert resultcodes.hresult_of(0)["hex"] == "0x00000000"
    assert resultcodes.hresult_of(0x80240034)["hex"] == "0x80240034"
    assert resultcodes.hresult_of(None) is None
    assert resultcodes.hresult_of("junk") == {"code": "junk", "hex": None}


def test_is_failed_covers_the_not_clean_endings():
    for code in (3, 4, 5):
        assert resultcodes.is_failed(resultcodes.result_of(code)) is True
    for code in (1, 2):
        assert resultcodes.is_failed(resultcodes.result_of(code)) is False
    assert resultcodes.is_failed(None) is False
    assert resultcodes.is_failed({"code": "junk", "meaning": None}) is False


# --- the entry shape --------------------------------------------------------

def test_entry_wraps_a_single_category_into_a_list():
    entry = tools._entry({"date": "2026-11-04T13:28:06.0000000", "title": "KB5000000",
                          "result_code": 2, "hresult": 0, "support_url": None,
                          "categories": "Microsoft Defender Antivirus"})
    assert entry["categories"] == ["Microsoft Defender Antivirus"]  # not one bare string
    assert entry["result"]["meaning"] == "it succeeded"
    assert entry["hresult"]["hex"] == "0x00000000"
    assert entry["support_url"] is None


def test_entry_clips_a_long_title_and_keeps_a_missing_one():
    long = "x" * 500
    entry = tools._entry({"title": long, "result_code": 4, "hresult": -1, "categories": []})
    assert len(entry["title"]) == tools.TITLE_CHARS + 1  # clip plus the ellipsis
    assert entry["title"].endswith("…")
    assert tools._entry({"title": None, "result_code": 4, "hresult": -1, "categories": None})["title"] is None


# --- the history tool, with the Agent faked ---------------------------------

HISTORY = {
    "total": 723,
    "entries": [
        {"date": "2026-11-04T13:28:06.0000000",
         "title": "Microsoft Defender Antivirus 的安全智能更新 - KB2267602（版本 1.463.121.0）",
         "result_code": 2, "hresult": 0, "support_url": "https://go.microsoft.com/fwlink/?LinkId=52661",
         "categories": ["Microsoft Defender Antivirus"]},
        {"date": "2026-11-03T09:00:00.0000000",
         "title": "Security Intelligence Update for Microsoft Defender - KB2267602 (1.459.670.0) failed",
         "result_code": 4, "hresult": -2145124300, "support_url": None, "categories": []},
        {"date": "2026-11-02T09:00:00.0000000",
         "title": "Security Intelligence Update - partial",  # succeeded with errors
         "result_code": 3, "hresult": 0, "support_url": None, "categories": []},
        {"date": "2026-11-01T09:00:00.0000000",
         "title": "Feature Update to Windows 11", "result_code": 2, "hresult": 0,
         "support_url": None, "categories": ["Windows 11"]},
    ],
}


@pytest.fixture()
def faked(monkeypatch):
    calls = {"take": []}

    def fake_history(take=wuquery.MAX_HISTORY):
        calls["take"].append(take)
        return {"total": HISTORY["total"],
                "entries": [dict(item) for item in HISTORY["entries"][:take]]}

    monkeypatch.setattr(tools.wuquery, "history", fake_history)
    return calls


def _load(text: str) -> dict:
    return json.loads(text)


def test_history_lists_newest_and_counts_the_not_clean(faked):
    answer = _load(tools.win_update_history({}))
    assert answer["ok"] is True
    assert len(answer["updates"]) == 4
    assert answer["updates"][0]["title"].startswith("Microsoft Defender")
    assert answer["updates"][1]["result"]["meaning"] == "it failed"
    assert answer["updates"][1]["hresult"]["hex"] == f"0x{-2145124300 & 0xFFFFFFFF:08X}"
    assert any("did not end clean" in note for note in answer["notes"])
    assert any("723 in the history" in note for note in answer["notes"])
    assert any("reaches back further" in note for note in answer["notes"])


def test_history_only_failures_keeps_three_four_five(faked):
    answer = _load(tools.win_update_history({"only_failures": True}))
    codes = [entry["result"]["code"] for entry in answer["updates"]]
    assert codes == [4, 3]


def test_history_query_substring_and_case(faked):
    answer = _load(tools.win_update_history({"query": "defender"}))
    assert len(answer["updates"]) == 2  # the Chinese title carries Defender's English name too
    nothing = _load(tools.win_update_history({"query": "no-such-update"}))
    assert nothing["updates"] == [] and any("nothing matched" in n for n in nothing["notes"])


def test_history_count_reaches_the_query_and_is_clamped(faked):
    answer = _load(tools.win_update_history({"count": 1}))
    assert len(answer["updates"]) == 1
    assert faked["take"] == [1]  # the caller's count reached the query itself
    tools.win_update_history({"count": 9999})
    assert faked["take"][-1] == tools.MAX_COUNT  # clamped, not passed through
    tools.win_update_history({"count": "junk"})
    assert faked["take"][-1] == 50  # a bad count falls back to the default


def test_history_empty_machine_is_an_answer_not_an_error(monkeypatch):
    monkeypatch.setattr(tools.wuquery, "history", lambda take=wuquery.MAX_HISTORY: {"total": 0, "entries": []})
    answer = _load(tools.win_update_history({"only_failures": True}))
    assert answer["ok"] is True
    assert answer["updates"] == []
    assert any("ended clean" in note for note in answer["notes"])


def test_history_agent_failure_is_a_clean_error(monkeypatch):
    def boom(take=wuquery.MAX_HISTORY):
        raise wuquery.PowerShellError("the Windows Update query failed: service disabled")

    monkeypatch.setattr(tools.wuquery, "history", boom)
    answer = _load(tools.win_update_history({}))
    assert answer["ok"] is False
    assert answer["code"] == "history_unavailable"
    assert "service disabled" in answer["error"]


def test_history_single_entry_survives_the_json_unwrapping(monkeypatch):
    # one entry arrives as a bare object, not a list; the query layer re-wraps it
    monkeypatch.setattr(tools.wuquery, "history",
                        lambda take=wuquery.MAX_HISTORY: {"total": 1, "entries": HISTORY["entries"][:1]})
    answer = _load(tools.win_update_history({}))
    assert len(answer["updates"]) == 1


# --- the hotfix tool, with CIM faked ----------------------------------------

HOTFIXES = [
    {"id": "KB5050575", "description": "Update", "installed_on": "2026-04-11",
     "installed_by": "NT AUTHORITY\\SYSTEM"},
    {"id": "KB5127694", "description": "Update", "installed_on": "2026-10-18",
     "installed_by": "NT AUTHORITY\\SYSTEM"},
    {"id": "KB5127648", "description": "Security Update", "installed_on": "2026-10-18",
     "installed_by": "NT AUTHORITY\\SYSTEM"},
    {"id": "KBOLD0001", "description": "Update", "installed_on": None, "installed_by": None},
]


@pytest.fixture()
def qfe_faked(monkeypatch):
    monkeypatch.setattr(tools.wuquery, "hotfixes", lambda: [dict(item) for item in HOTFIXES])


def test_hotfix_table_sorts_newest_first_and_undated_last(qfe_faked):
    answer = _load(tools.win_hotfix_table({}))
    assert answer["ok"] is True
    ids = [row["id"] for row in answer["hotfixes"]]
    assert ids == ["KB5127694", "KB5127648", "KB5050575", "KBOLD0001"]  # newest date first, same-day ties by id, undated last
    assert any("OS-level" in note for note in answer["notes"])


def test_hotfix_table_query_and_limit(qfe_faked):
    answer = _load(tools.win_hotfix_table({"query": "5127"}))
    assert [row["id"] for row in answer["hotfixes"]] == ["KB5127694", "KB5127648"]
    limited = _load(tools.win_hotfix_table({"limit": 1}))
    assert len(limited["hotfixes"]) == 1
    assert any("stopped at limit" in note for note in limited["notes"])


def test_hotfix_table_empty_list_is_an_answer(monkeypatch):
    monkeypatch.setattr(tools.wuquery, "hotfixes", lambda: [])
    answer = _load(tools.win_hotfix_table({}))
    assert answer["ok"] is True
    assert answer["hotfixes"] == []
    assert any("nothing matched" in note for note in answer["notes"])


def test_hotfix_table_failure_is_a_clean_error(monkeypatch):
    def boom():
        raise wuquery.PowerShellError("the Windows Update query failed: CIM refused")

    monkeypatch.setattr(tools.wuquery, "hotfixes", boom)
    answer = _load(tools.win_hotfix_table({}))
    assert answer["ok"] is False
    assert answer["code"] == "hotfixes_unavailable"


# --- what a machine without these APIs sees ---------------------------------

def test_module_imports_without_windows():
    """The catalog's Linux validator imports the plugin where PowerShell and COM do not
    exist: nothing here touches a platform module at import time, and the query layer
    only reaches for the outside world inside a tool call."""
    import importlib
    import subprocess as real_subprocess

    # the runner holds a plain string constant and defers every subprocess call to
    # tool time; importing the package must not spawn anything
    saved_run = real_subprocess.run
    real_subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned at import"))
    try:
        importlib.reload(wuquery)
        importlib.reload(tools)
    finally:
        real_subprocess.run = saved_run
        importlib.reload(wuquery)
        importlib.reload(tools)
