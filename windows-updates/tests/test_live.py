"""Live tests: the real Windows Update Agent and CIM, on this machine."""

from __future__ import annotations

import datetime as dt
import json

import pytest

pytestmark = pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="live Windows Update history only"
)

from hermes_windows_updates import resultcodes, tools, wuquery  # noqa: E402


def _iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def test_the_agent_answers_and_the_order_is_newest_first():
    answer = wuquery.history(10)
    assert answer["total"] >= 1  # every Windows install carries some history
    entries = answer["entries"]
    assert 1 <= len(entries) <= 10
    dates = [_iso(entry["date"]) for entry in entries if entry.get("date")]
    assert dates == sorted(dates, reverse=True)
    for entry in entries:
        assert isinstance(entry.get("title"), str) and entry["title"]
        assert int(entry.get("result_code")) in {1, 2, 3, 4, 5}


def test_the_history_matches_the_settings_page_semantics():
    """The newest entry must parse as a moment within the last year and carry a
    decodable result; this is the same stream Settings > Windows Update > Update
    history renders."""
    answer = wuquery.history(1)
    entry = answer["entries"][0]
    when = _iso(entry["date"])
    assert dt.datetime.now() - when < dt.timedelta(days=365)
    assert entry["result_code"] in {1, 2, 3, 4, 5}
    assert isinstance(entry.get("categories"), list)


def test_history_tool_end_to_end():
    payload = json.loads(tools.win_update_history({"count": 5}))
    assert payload["ok"] is True
    assert len(payload["updates"]) <= 5
    assert any("in the history" in note for note in payload["notes"])
    for update in payload["updates"]:
        assert update["result"]["meaning"] is not None
        assert update["hresult"]["hex"].startswith("0x")


def test_history_only_failures_lists_not_clean_endings():
    payload = json.loads(tools.win_update_history({"count": 500, "only_failures": True}))
    assert payload["ok"] is True
    for update in payload["updates"]:
        assert resultcodes.is_failed(update["result"])
        assert update["hresult"]["code"] != 0 or update["result"]["code"] == 3


def test_hotfixes_from_cim():
    rows = wuquery.hotfixes()
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row.get("id"), str) and row["id"]
        if row.get("installed_on"):
            dt.date.fromisoformat(row["installed_on"])  # the fixed yyyy-MM-dd spelling


def test_hotfix_tool_end_to_end():
    payload = json.loads(tools.win_hotfix_table({}))
    assert payload["ok"] is True
    dated = [row["installed_on"] for row in payload["hotfixes"] if row["installed_on"]]
    assert dated == sorted(dated, reverse=True)
    assert any("win_update_history" in note for note in payload["notes"])
