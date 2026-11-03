"""Live tests: the real registry and Startup folders, on this machine."""

from __future__ import annotations

import json
import time

import pytest

pytestmark = pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="live Windows autostart only"
)

from hermes_windows_startup import startupdirs, startupreg, tools  # noqa: E402


def test_the_run_keys_and_folders_hold_up():
    entries = startupreg.run_entries()
    assert len(entries) >= 2  # a real install carries at least SecurityHealth and one more
    known_sources = {source for _which, _path, source, _scope in startupreg.RUN_SOURCES}
    for entry in entries:
        assert entry["source"] in known_sources
        assert entry["scope"] in {"user", "machine"}
        assert isinstance(entry["command"], str)

    folders = startupdirs.folders(startupreg.shell_folder)
    assert isinstance(folders, list)  # folders may legitimately be empty


def test_the_approval_records_read_back():
    approvals = startupreg.approvals()
    assert len(approvals) >= 1
    for (_source, _name), facts in approvals.items():
        assert facts["state"] in {"enabled", "disabled"} or facts["state"].startswith("unknown")
        assert facts["changed"] is None or facts["changed"].endswith("+00:00") or "T" in facts["changed"]


def test_shell_folders_exist_on_this_machine():
    import os

    user = startupreg.shell_folder("Startup", "nowhere")
    assert os.path.isdir(user)
    common = startupreg.shell_folder("Common Startup", "nowhere", which="hklm")
    assert os.path.isdir(common)


def test_the_table_answers_fast_and_honestly():
    started = time.perf_counter()
    answer = json.loads(tools.win_startup_table({}))
    elapsed = time.perf_counter() - started
    assert answer["ok"] is True
    assert len(answer["startup"]) >= 2
    assert elapsed < 2.0  # registry + two folders, no PowerShell anywhere
    assert answer["notes"]


def test_the_detail_resolves_a_real_entry():
    table = json.loads(tools.win_startup_table({}))
    name = table["startup"][0]["name"]
    answer = json.loads(tools.win_startup_detail({"name": str(name).lower()}))
    assert answer["ok"] is True
    assert answer["name"] == name
    assert answer["enabled"] in {"enabled", "disabled"} or str(answer["enabled"]).startswith("unknown")
    # a real machine resolves well-known binaries to disk
    assert answer["binary"] is None or isinstance(answer["binary"]["path"], str)
