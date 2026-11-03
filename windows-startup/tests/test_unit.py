"""Unit tests: every layer with fakes, no registry, no folders."""

from __future__ import annotations

import json
import struct

import pytest

from hermes_windows_startup import startupdirs, startupreg, tools


# --- fakes ------------------------------------------------------------------

class _FakeKey:
    def __init__(self, values):
        self._values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _enum(key, index):
    items = sorted(key._values.items())
    if index >= len(items):
        raise OSError("no more values")
    name, data = items[index]
    return name, data, 1


def _opener_with(table):
    """A winreg.OpenKey stand-in answering from {(hive, path): {name: data}}."""

    def open_key(hive, path):
        if (hive, path) in table:
            return _FakeKey(table[(hive, path)])
        raise OSError("no such key")

    return open_key


def _blob(state_byte: int, stamp: int = 0) -> bytes:
    return bytes([state_byte, 0, 0, 0]) + struct.pack("<Q", stamp)


@pytest.fixture()
def registry(monkeypatch):
    """The registry layer runs its real code over a fake hive tree."""
    monkeypatch.setattr(startupreg, "_hive", lambda which: which)
    monkeypatch.setattr(startupreg.winreg, "EnumValue", _enum)

    table = {
        ("hkcu", startupreg.RUN_PATH): {
            "CC Switch": "C:\\Users\\me\\AppData\\Local\\Programs\\CC Switch\\cc-switch.exe ",
            "OffApp": '"C:\\Program Files\\Off\\off.exe" /background',
        },
        ("hklm", startupreg.RUN_PATH): {
            "SecurityHealth": "%windir%\\system32\\SecurityHealthSystray.exe"
        },
        ("hkcu", startupreg.APPROVED_PATH + "\\Run"): {
            "CC Switch": _blob(2),
            "OffApp": _blob(6, stamp=134116992000000000),  # 2026-01-01 UTC
            "EgoAutoLaunch_ORPHAN": _blob(1, stamp=132900000000000000),
        },
    }

    real_run_entries, real_approvals, real_shell_folder = (
        startupreg.run_entries, startupreg.approvals, startupreg.shell_folder)
    bound = _opener_with(table)
    monkeypatch.setattr(startupreg, "run_entries", lambda opener=None: real_run_entries(opener=bound))
    monkeypatch.setattr(startupreg, "approvals", lambda opener=None: real_approvals(opener=bound))
    monkeypatch.setattr(
        startupreg, "shell_folder",
        lambda value_name, default, which="hkcu", opener=None: real_shell_folder(
            value_name, default, which, bound))
    return table


# --- the registry layer -----------------------------------------------------

def test_run_entries_cover_all_six_sources(registry):
    entries = startupreg.run_entries(_opener_with(registry))
    assert {e["source"] for e in entries} == {"registry-hkcu-run", "registry-hklm-run"}
    hkcu = next(e for e in entries if e["name"] == "CC Switch")
    assert hkcu["scope"] == "user"
    assert hkcu["command"].endswith("cc-switch.exe ")  # trailing space survives verbatim
    hklm = next(e for e in entries if e["name"] == "SecurityHealth")
    assert hklm["scope"] == "machine"
    # keys absent from the fake (RunOnce, WOW64) answer empty, never raise
    assert all("runonce" not in e["source"] for e in entries)


def test_approvals_decode_states_and_when(registry):
    approvals = startupreg.approvals(_opener_with(registry))
    assert approvals[("registry-hkcu-run", "CC Switch")]["state"] == "enabled"
    off = approvals[("registry-hkcu-run", "OffApp")]
    assert off["state"] == "disabled"
    assert off["changed"].startswith("2026")
    unknown = approvals[("registry-hkcu-run", "EgoAutoLaunch_ORPHAN")]
    assert unknown["state"].startswith("unknown")


def test_shell_folder_expands_and_falls_back(registry):
    where = startupreg.shell_folder("Startup", "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup",
                                     opener=_opener_with(registry))
    assert "AppData" in where  # %USERPROFILE% expanded
    missing = startupreg.shell_folder("Not Set", "%ProgramData%\\x", opener=_opener_with(registry))
    assert missing.endswith("\\x")


def test_run_entries_without_winreg_raise_an_answer(monkeypatch):
    monkeypatch.setattr(startupreg, "winreg", None)
    with pytest.raises(startupreg.RegistryUnavailable):
        startupreg.run_entries()


# --- the folder layer --------------------------------------------------------

def test_scan_lists_files_and_skips_desktop_ini(tmp_path):
    (tmp_path / "thing.lnk").write_bytes(b"x")
    (tmp_path / "desktop.ini").write_bytes(b"x")
    entries = startupdirs.scan(str(tmp_path), "folder-user", "user")
    assert [e["name"] for e in entries] == ["thing.lnk"]
    assert entries[0]["file"]["size"] == 1
    assert entries[0]["file"]["modified"] is not None


def test_folders_read_both_dirs_honoring_redirects(tmp_path):
    user = tmp_path / "user"
    common = tmp_path / "common"
    user.mkdir()
    common.mkdir()
    (user / "mine.lnk").write_bytes(b"x")
    (common / "everyone.cmd").write_bytes(b"x")

    def fake_shell_folder(value_name, default, which="hkcu", opener=None):
        assert which == ("hkcu" if value_name == "Startup" else "hklm")
        return str(user if value_name == "Startup" else common)

    entries = startupdirs.folders(fake_shell_folder)
    assert {(e["name"], e["source"], e["scope"]) for e in entries} == {
        ("mine.lnk", "folder-user", "user"),
        ("everyone.cmd", "folder-common", "machine"),
    }


# --- the tools, with registry and folders faked ------------------------------

@pytest.fixture()
def faked(registry, monkeypatch, tmp_path):
    """One coherent world: the fake registry plus one real folder."""
    user = tmp_path / "Startup"
    user.mkdir()
    (user / "gone.lnk").write_bytes(b"x")
    monkeypatch.setattr(tools.startupdirs, "folders", lambda shell_folder_fn: startupdirs.scan(
        str(user), "folder-user", "user"))
    monkeypatch.setattr(tools.os.path, "isfile", lambda p: not str(p).lower().endswith(("gone.exe", "off.exe")))


def _load(text: str) -> dict:
    return json.loads(text)


def test_table_lists_filters_and_reports_orphans(faked):
    answer = _load(tools.win_startup_table({}))
    assert answer["ok"] is True
    names = {row["name"] for row in answer["startup"]}
    assert {"CC Switch", "OffApp", "SecurityHealth", "gone.lnk"} <= names

    by_name = {row["name"]: row for row in answer["startup"]}
    assert by_name["CC Switch"]["enabled"] == "enabled"
    assert by_name["OffApp"]["enabled"] == "disabled"
    assert by_name["gone.lnk"]["enabled"] == "enabled"  # no record means it runs
    assert by_name["OffApp"]["changed"].startswith("2026")
    assert by_name["SecurityHealth"]["scope"] == "machine"
    assert by_name["CC Switch"]["scope"] == "user"

    orphans = answer["leftover_approvals"]
    assert [o["name"] for o in orphans] == ["EgoAutoLaunch_ORPHAN"]
    assert any("left behind" in note or "left over" in note or "gone" in note for note in answer["notes"])

    only_machine = _load(tools.win_startup_table({"scope": "machine"}))
    assert {row["name"] for row in only_machine["startup"]} == {"SecurityHealth"}

    no_disabled = _load(tools.win_startup_table({"include_disabled": False}))
    assert "OffApp" not in {row["name"] for row in no_disabled["startup"]}
    assert any("switched off" in note for note in no_disabled["notes"])

    narrow = _load(tools.win_startup_table({"query": "securityhealth"}))
    assert [row["name"] for row in narrow["startup"]] == ["SecurityHealth"]


def test_table_limit_and_notes(faked):
    answer = _load(tools.win_startup_table({"limit": 1}))
    assert len(answer["startup"]) == 1
    assert any("stopped at limit" in note for note in answer["notes"])
    nothing = _load(tools.win_startup_table({"query": "nothing-matches"}))
    assert nothing["startup"] == [] and any("nothing matched" in n for n in nothing["notes"])
    bad_scope = _load(tools.win_startup_table({"scope": "sideways"}))
    assert any("scope is one of" in note for note in bad_scope["notes"])


def test_detail_resolves_the_binary_and_tells_the_verdict(faked):
    answer = _load(tools.win_startup_detail({"name": "offapp"}))
    assert answer["ok"] is True
    assert answer["enabled"] == "disabled"
    assert answer["binary"]["path"].endswith("off.exe")
    assert answer["binary"]["present"] is False
    assert any("not on disk" in note for note in answer["notes"])
    assert any("switched off" in note for note in answer["notes"])

    unquoted = _load(tools.win_startup_detail({"name": "CC Switch"}))
    assert unquoted["binary"]["path"].endswith("cc-switch.exe")  # trailing space did not bite


def test_detail_names_and_suggests(faked):
    no_name = _load(tools.win_startup_detail({}))
    assert no_name["code"] == "name_required"
    missing = _load(tools.win_startup_detail({"name": "does-not-exist"}))
    assert missing["ok"] is False
    assert missing["code"] == "not_registered"
    near = _load(tools.win_startup_detail({"name": "security"}))
    assert near["ok"] is True
    assert near["name"] == "SecurityHealth"


def test_module_imports_where_winreg_does_not_exist(monkeypatch):
    """The catalog's Linux validator imports the plugin with no winreg present:
    nothing may touch winreg at import time, and a missing registry is a raised,
    answerable error, not a crash."""
    import importlib
    import sys

    class _Blocked:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "winreg":
                raise ImportError("blocked: simulating a non-Windows import")
            return None

    blocker = _Blocked()
    saved = sys.modules.pop("winreg", None)
    sys.meta_path.insert(0, blocker)
    try:
        importlib.reload(startupreg)
        assert startupreg.winreg is None
        with pytest.raises(startupreg.RegistryUnavailable):
            startupreg.run_entries()
    finally:
        sys.meta_path.remove(blocker)
        if saved is not None:
            sys.modules["winreg"] = saved
        importlib.reload(startupreg)
