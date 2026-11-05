"""Unit tests: every layer with fakes, no real registry anywhere."""

from __future__ import annotations

import json

import pytest

from hermes_windows_apps import appreg, tools


# --- fakes -------------------------------------------------------------------

def _key(subkeys=None, values=None):
    return {"subkeys": subkeys or {}, "values": values or {}}


def _open(table, denied=()):
    """A winreg.OpenKey stand-in: answers at the longest registered prefix,
    then walks subkey nodes the way a real registry path does."""

    def open_key(hive, path):
        if (hive, path) in denied:
            raise OSError("access denied")
        parts = str(path).split("\\")
        node = None
        rest: list[str] = []
        for size in range(len(parts), 0, -1):
            prefix = (hive, "\\".join(parts[:size]))
            if prefix in table:
                node = table[prefix]
                rest = parts[size:]
                break
        if node is None:
            raise OSError("no such key")
        for part in rest:
            if part not in node["subkeys"]:
                raise OSError("no such key")
            node = node["subkeys"][part]
        return _FakeKey(node)

    return open_key


class _FakeKey:
    def __init__(self, node):
        self._node = node

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _enum_key(key, index):
    items = sorted(key._node["subkeys"])
    if index >= len(items):
        raise OSError("no more subkeys")
    return items[index]


def _query(key, name):
    values = key._node["values"]
    if name not in values:
        raise FileNotFoundError(name)
    data, kind = values[name]
    return data, kind


@pytest.fixture()
def registry(monkeypatch):
    """The registry layer runs its real code over a fake hive tree."""
    monkeypatch.setattr(appreg, "_hive", lambda which: which)
    monkeypatch.setattr(appreg.winreg, "EnumKey", _enum_key)
    monkeypatch.setattr(appreg.winreg, "QueryValueEx", _query)

    u64 = appreg.UNINSTALL_PATH
    u32 = appreg.WOW64_UNINSTALL_PATH
    table = {
        ("hklm", u64): _key(subkeys={
            "OBS Studio": _key(values={
                "DisplayName": ("OBS Studio", 1),
                "DisplayVersion": ("31.1.0", 1),
                "Publisher": ("OBS Project", 1),
                "EstimatedSize": (250000, 4),  # KB -> 244.1 MB
                "InstallDate": ("20250102", 1),
                "UninstallString": (
                    'MsiExec.exe /I{677B017D-A65C-4B28-8D4B-59AE7F7ED6E6}', 1),
                "WindowsInstaller": (1, 4),
            }),
            "VC Redist x64": _key(values={
                "DisplayName": ("Microsoft Visual C++ 2015-2022 Redistributable (x64)", 1),
                "SystemComponent": (1, 4),
                "UninstallString": (
                    "MsiExec.exe /X{A65C4288-8D4B-4B28-59AE-F7ED6E76B017}", 1),
            }),
            "Locked Thing": _key(values={"DisplayName": ("Security Suite", 1)}),
        }),
        ("hklm", u32): _key(subkeys={
            "OBS Studio": _key(values={
                "DisplayName": ("OBS Studio", 1),
                "DisplayVersion": ("30.2.3", 1),
                "UninstallString": ("C:\\Program Files (x86)\\OBS\\uninstall.exe", 1),
            }),
            "Old Tool": _key(values={
                "DisplayName": ("Old Tool", 1),
                "Publisher": ("Legacy Soft", 1),
                "InstallDate": ("1/2/2025", 1),
                "InstallLocation": ("C:\\Program Files (x86)\\Old Tool", 1),
                "UninstallString": ('"C:\\Program Files (x86)\\Old Tool\\setup.exe" -remove', 1),
                "NoModify": (1, 4),
                "NoRepair": (1, 4),
            }),
        }),
        ("hkcu", u64): _key(subkeys={
            "My App": _key(values={
                "DisplayName": ("My App", 1),
                "DisplayVersion": ("2.0", 1),
                "InstallLocation": ("C:\\Gone\\My App", 1),
                "UninstallString": ("C:\\Users\\me\\AppData\\Local\\MyApp\\unin.exe", 1),
            }),
            "Cleanup Helper": _key(values={
                "DisplayName": ("Cleanup Helper", 1),
                "UninstallString": ("C:\\Users\\me\\clean.cmd", 1),
            }),
            "Bare Runtime": _key(values={
                "DisplayName": ("Bare Runtime", 1),
                "WindowsInstaller": (1, 4),
            }),
            "Orphan Stub": _key(values={
                "DisplayName": ("Orphan Stub", 1),
            }),
        }),
        # ("hkcu", u32): absent -- a real machine can lack it; the sweep reports empty
    }

    denied = {(("hklm"), u64 + "\\Locked Thing")}
    bound_open = _open(table, denied)
    real_app_entries = appreg.app_entries
    monkeypatch.setattr(
        appreg, "app_entries",
        lambda opener=None, query=None: real_app_entries(opener=bound_open, query=_query))
    monkeypatch.setattr(tools.os.path, "isdir", lambda p: not str(p).lower().startswith("c:\\gone"))
    return table


def _load(text: str) -> dict:
    return json.loads(text)


# --- the registry layer ------------------------------------------------------

def test_app_entries_cover_the_views_and_flag_the_unreadable(registry):
    entries = appreg.app_entries()
    views = {e["view"] for e in entries}
    assert {"machine-64", "machine-32", "user-64"} <= views
    assert "user-32" not in views  # the key does not exist: empty, never an error
    locked = next(e for e in entries if e.get("subkey") == "Locked Thing")
    assert locked["unreadable"] is True
    names = {str(e.get("displayname")) for e in entries if not e.get("unreadable")}
    assert "OBS Studio" in names and "My App" in names


def test_hidden_entries_are_marked():
    assert tools._dwordish(1) is True
    assert tools._dwordish("1") is True
    assert tools._dwordish(0) is False
    assert tools._dwordish(None) is False
    entry = {"displayname": "x", "systemcomponent": 1, "views": ["machine-64"]}
    assert tools._is_hidden(entry) is True


def test_size_and_date_reading():
    assert tools._size_mb(250000) == 244.1
    assert tools._size_mb(None) is None
    assert tools._install_date("20250102") == "2025-01-02"
    assert tools._install_date("1/2/2025") == "2025-01-02"
    assert tools._install_date("not a date") == "not a date"  # verbatim, not guessed
    assert tools._install_date(None) is None


def test_uninstaller_classification_matrix():
    msi = tools._classify_uninstaller("MsiExec.exe /X{GUID}", False)
    assert msi["kind"] == "msiexec"
    setup = tools._classify_uninstaller('"C:\\x\\setup.exe" -remove', False)
    assert setup["kind"] == "setup executable"
    script = tools._classify_uninstaller("C:\\x\\clean.cmd", False)
    assert script["kind"] == "script"
    appx = tools._classify_uninstaller("PowerShell RemoveAppxPackage X", False)
    assert appx["kind"] == "appx"
    assert tools._classify_uninstaller(None, True)["kind"] == "windows installer"
    assert tools._classify_uninstaller(None, False) is None


def test_app_entries_without_winreg_raise_an_answer(monkeypatch):
    monkeypatch.setattr(appreg, "winreg", None)
    with pytest.raises(appreg.RegistryUnavailable):
        appreg.app_entries()


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
        importlib.reload(appreg)
        assert appreg.winreg is None
        with pytest.raises(appreg.RegistryUnavailable):
            appreg.app_entries()
    finally:
        sys.meta_path.remove(blocker)
        if saved is not None:
            sys.modules["winreg"] = saved
        importlib.reload(appreg)


# --- the tools, with the registry faked --------------------------------------

def test_table_lists_filters_hidden_and_answers_queries(registry):
    answer = _load(tools.win_app_table({}))
    assert answer["ok"] is True
    names = {row["name"] for row in answer["apps"]}
    assert {"OBS Studio", "Old Tool", "My App", "Cleanup Helper", "Bare Runtime"} <= names
    assert "Microsoft Visual C++ 2015-2022 Redistributable (x64)" not in names  # hidden
    assert any("hidden from Apps & Features" in note for note in answer["notes"])
    assert "Locked Thing" in answer["unreadable"]

    with_hidden = _load(tools.win_app_table({"include_system_components": True}))
    assert "Microsoft Visual C++ 2015-2022 Redistributable (x64)" in {
        row["name"] for row in with_hidden["apps"]}

    obs = _load(tools.win_app_table({"query": "obs"}))
    assert [row["name"] for row in obs["apps"]] == ["OBS Studio"]
    by_publisher = _load(tools.win_app_table({"query": "legacy"}))
    assert [row["name"] for row in by_publisher["apps"]] == ["Old Tool"]


def test_table_collapses_the_dual_install(registry):
    answer = _load(tools.win_app_table({"query": "obs"}))
    row = answer["apps"][0]
    assert row["views"] == ["machine-64", "machine-32"]
    assert row["view"] == "machine-64"  # the first view read stays primary
    assert any("dual install" in note for note in answer["notes"])


def test_table_view_filter_and_bad_view(registry):
    only32 = _load(tools.win_app_table({"view": "machine-32"}))
    assert {row["name"] for row in only32["apps"]} == {"OBS Studio", "Old Tool"}
    bad = _load(tools.win_app_table({"view": "sideways"}))
    assert any("view is one of" in note for note in bad["notes"])


def test_table_limit_and_no_match(registry):
    limited = _load(tools.win_app_table({"limit": 1}))
    assert len(limited["apps"]) == 1
    assert any("stopped at limit" in note for note in limited["notes"])
    nothing = _load(tools.win_app_table({"query": "nothing-matches"}))
    assert nothing["apps"] == []
    assert any("nothing matched" in note for note in nothing["notes"])


def test_table_reads_size_and_both_date_shapes(registry):
    answer = _load(tools.win_app_table({}))
    by_name = {row["name"]: row for row in answer["apps"]}
    assert by_name["OBS Studio"]["size_mb"] == 244.1
    assert by_name["OBS Studio"]["installed"] == "2025-01-02"
    assert by_name["Old Tool"]["installed"] == "2025-01-02"  # localized shape


def test_detail_shows_occurrences_and_classifications(registry):
    obs = _load(tools.win_app_detail({"name": "obs studio"}))
    assert obs["ok"] is True
    assert obs["msi_managed"] is True
    assert len(obs["occurrences"]) == 2
    kinds = {o["view"]: o["uninstaller"]["kind"] for o in obs["occurrences"]}
    assert kinds["machine-64"] == "msiexec"
    assert kinds["machine-32"] == "setup executable"
    assert any("dual-install" in note or "dual install" in note for note in obs["notes"])

    old = _load(tools.win_app_detail({"name": "Old Tool"}))
    location = old["occurrences"][0]["install_location"]
    assert location["exists"] is True
    assert any("locked modification and repair" in note for note in old["notes"])


def test_detail_flags_the_leftover_and_the_bare(registry):
    gone = _load(tools.win_app_detail({"name": "my app"}))
    assert gone["occurrences"][0]["install_location"]["exists"] is False
    assert any("not on disk" in note for note in gone["notes"])

    bare = _load(tools.win_app_detail({"name": "bare runtime"}))
    assert bare["occurrences"][0]["uninstall_string"] is None
    assert bare["occurrences"][0]["uninstaller"]["kind"] == "windows installer"

    orphan = _load(tools.win_app_detail({"name": "orphan stub"}))
    assert orphan["occurrences"][0]["uninstaller"] is None
    assert any("no uninstall command" in note for note in orphan["notes"])


def test_detail_names_and_suggests(registry):
    no_name = _load(tools.win_app_detail({}))
    assert no_name["code"] == "name_required"
    missing = _load(tools.win_app_detail({"name": "does-not-exist"}))
    assert missing["ok"] is False
    assert missing["code"] == "not_installed"
    near = _load(tools.win_app_detail({"name": "old"}))
    assert near["ok"] is True
    assert near["name"] == "Old Tool"
