"""Live tests: the real Uninstall keys, on this machine."""

from __future__ import annotations

import json
import time

import pytest

pytestmark = pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="live Windows registry only"
)

from hermes_windows_apps import appreg, tools  # noqa: E402


def test_the_four_keys_sweep_the_machine():
    entries = appreg.app_entries()
    assert len(entries) >= 10  # a real install carries far more than this
    views = {e["view"] for e in entries}
    assert views <= {view for _which, _path, view in appreg.UNINSTALL_SOURCES}
    assert "machine-64" in views
    for entry in entries:
        if entry.get("unreadable"):
            continue
        assert entry["subkey"]
        # a real machine writes real names; hidden entries can carry None only
        # where the publisher skipped the field entirely, which collapse drops


def test_real_entries_carry_publisher_facts():
    entries = [e for e in appreg.app_entries() if not e.get("unreadable")]
    named = [e for e in entries if e.get("displayname")]
    assert named
    with_publisher = [e for e in named if e.get("publisher")]
    assert with_publisher  # any real inventory has publisher-annotated entries
    with_uninstaller = [e for e in named if e.get("uninstallstring")]
    assert with_uninstaller
    sized = [e for e in named if isinstance(e.get("estimatedsize"), int)]
    assert sized  # EstimatedSize is written as a DWORD in the wild
    dated = [e for e in named if e.get("installdate")]
    assert dated
    for entry in dated:
        parsed = tools._install_date(entry["installdate"])
        assert parsed is not None


def test_hidden_entries_exist_on_a_real_machine():
    """Runtimes and update rollups carry SystemComponent=1 everywhere."""
    entries = [e for e in appreg.app_entries() if not e.get("unreadable")]
    hidden = [e for e in entries if tools._dwordish(e.get("systemcomponent"))]
    assert hidden  # every real Windows install hides its VC runtimes this way


def test_the_table_answers_fast_and_honestly():
    started = time.perf_counter()
    answer = json.loads(tools.win_app_table({}))
    elapsed = time.perf_counter() - started
    assert answer["ok"] is True
    assert len(answer["apps"]) >= 20  # hundreds on this class of machine
    assert elapsed < 2.0  # four keys, no PowerShell, no WMI
    assert answer["notes"]
    for row in answer["apps"]:
        assert row["name"]
        assert row["view"] in tools.VIEWS
        if "views" in row:
            assert row["view"] in row["views"] and len(row["views"]) > 1


def test_the_detail_resolves_a_real_program():
    table = json.loads(tools.win_app_table({}))
    name = table["apps"][0]["name"]
    answer = json.loads(tools.win_app_detail({"name": str(name).lower()}))
    assert answer["ok"] is True
    assert answer["name"] == name
    assert answer["occurrences"]
    for occurrence in answer["occurrences"]:
        assert occurrence["view"] in tools.VIEWS
        if occurrence["uninstaller"] is not None:
            assert occurrence["uninstaller"]["kind"]
