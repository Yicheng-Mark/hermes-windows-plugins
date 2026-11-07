"""Live tests: the real storage stack, unelevated, on the machine itself."""

from __future__ import annotations

import json
import platform
import time

import pytest

from hermes_windows_disks import diskquery, tools

pytestmark = pytest.mark.skipif(platform.system() != "Windows",
                                reason="the storage classes are Windows-only")


def test_one_session_answers_the_whole_machine():
    started = time.perf_counter()
    raw = diskquery.query()
    elapsed = time.perf_counter() - started
    assert raw["physical"], "no physical disk answered"
    assert raw["volumes"], "no volume answered"
    assert elapsed < 30, f"the single session took {elapsed:.1f}s"


def test_table_on_the_real_machine():
    out = json.loads(tools.win_disk_table({}))
    assert out["ok"] is True
    drives = {row.get("drive") for row in out["rows"] if row["kind"] == "volume"}
    assert "C:" in drives, "the system volume is missing"
    disks = [row for row in out["rows"] if row["kind"] == "disk"]
    assert disks and disks[0]["media"] in {"ssd", "hdd", "scm", "unspecified"}


def test_letterless_volumes_hidden_until_asked():
    plain = json.loads(tools.win_disk_table({}))
    shown = json.loads(tools.win_disk_table({"include_letterless": True}))
    letterless_plain = [row for row in plain["rows"]
                        if row["kind"] == "volume" and not row.get("drive")]
    letterless_shown = [row for row in shown["rows"]
                        if row["kind"] == "volume" and not row.get("drive")]
    assert not letterless_plain
    assert letterless_shown, "the EFI or recovery volume should appear when asked for"


def test_detail_round_trips_by_letter_and_by_model():
    by_letter = json.loads(tools.win_disk_detail({"target": "C:"}))
    assert by_letter["matched"] == "volume" and "%" in by_letter["free_space"]
    disks = json.loads(tools.win_disk_table({"kind": "disk"}))["rows"]
    model = disks[0]["model"].split()[0]
    by_model = json.loads(tools.win_disk_detail({"target": model}))
    assert by_model["matched"] == "disk"
    assert by_model["partitions"], "a real disk has partitions"
    assert all(p["type"] for p in by_model["partitions"])


def test_unknown_health_carries_the_operational_note():
    out = json.loads(tools.win_disk_table({}))
    unknown = [row for row in out["rows"]
               if row["kind"] == "disk" and row["health"] == "unknown"]
    if unknown:  # the writing machine's healthy NVMe answers exactly this
        assert any("OperationalStatus is the other signal" in note for note in out["notes"])
