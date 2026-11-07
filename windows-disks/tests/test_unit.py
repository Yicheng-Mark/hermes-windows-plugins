"""Unit tests: every layer with fakes - no PowerShell, no CIM.

The fixtures are the shapes the writing machine really answered (a one-disk NVMe
GPT layout whose health word reads unknown while OperationalStatus says ok) and
a richer two-disk shape that covers mbr type bytes, a network volume with a UNC,
and the free-space thresholds.
"""

from __future__ import annotations

import json

import pytest

from hermes_windows_disks import diskquery, enums, tools


def _sizes(capacity_gib: float, free_pct: float) -> tuple[int, int]:
    capacity = int(capacity_gib * 1024 ** 3)
    return capacity, int(capacity * free_pct / 100.0)


# --- the writing machine's answer, as the PowerShell layer delivers it --------

C_CAP, C_FREE = _sizes(500.0, 69.5)
D_CAP, D_FREE = _sizes(451.4, 92.1)

MACHINE = {
    "physical": [
        {"id": "0", "model": "UMIS RPJYJ1T24RLS1QWY", "serial": "5CDF_B805_81C0_557D.",
         "media": 4, "bus": 17, "health": 0, "op": [2], "size": 1024209543168, "spindle": 0},
    ],
    "disks": [
        {"number": 0, "style": 2, "guid": "{fafaa0d1-d86c-4c3d-b7bc-e8563af46118}",
         "boot": True, "system": True, "readonly": False, "partitions": 5,
         "free_extent": 0, "size": 1024209543168},
    ],
    "parts": [
        {"disk": 0, "partition": 1, "letter": None, "offset": 1048576, "size": 272629760,
         "gpt": "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}", "mbr": None, "boot": False, "system": True},
        {"disk": 0, "partition": 2, "letter": None, "offset": 273678336, "size": 16777216,
         "gpt": "{e3c9e316-0b5c-4db8-817d-f92df00215ae}", "mbr": None, "boot": False, "system": False},
        {"disk": 0, "partition": 3, "letter": "C", "offset": 290455552, "size": 536871960576,
         "gpt": "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}", "mbr": None, "boot": True, "system": False},
        {"disk": 0, "partition": 4, "letter": "D", "offset": 537162416128, "size": 484949622784,
         "gpt": "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}", "mbr": None, "boot": False, "system": False},
        {"disk": 0, "partition": 5, "letter": None, "offset": 1022112038912, "size": 2097152000,
         "gpt": "{de94bba4-06d1-4d40-a16a-bfd50179d6ac}", "mbr": None, "boot": False, "system": False},
    ],
    "volumes": [
        {"letter": "C:", "label": "Windows-SSD", "fs": "NTFS", "capacity": C_CAP, "free": C_FREE,
         "drive_type": 3, "guid": "\\\\?\\Volume{6d21fc96}\\"},
        {"letter": "D:", "label": "Data", "fs": "NTFS", "capacity": D_CAP, "free": D_FREE,
         "drive_type": 3, "guid": "\\\\?\\Volume{38ab9abf}\\"},
        {"letter": None, "label": "WINRE_DRV", "fs": "NTFS", "capacity": 2097147904,
         "free": 1076379648, "drive_type": 3, "guid": "\\\\?\\Volume{db0b9e4e}\\"},
        {"letter": None, "label": "SYSTEM_DRV", "fs": "FAT32", "capacity": 268435456,
         "free": 220168192, "drive_type": 3, "guid": "\\\\?\\Volume{94a8fcd5}\\"},
    ],
    "netconns": [],
}

X_CAP, X_FREE = _sizes(1000.0, 9.4)   # low
Y_CAP, Y_FREE = _sizes(500.0, 4.2)    # critical
Z_CAP, Z_FREE = _sizes(2000.0, 55.0)  # network

RICH = {
    "physical": [
        {"id": "0", "model": "Samsung SSD 990 PRO", "serial": "S6Z1NJ0R123456",
         "media": 4, "bus": 17, "health": 1, "op": [2], "size": 1000204886016, "spindle": 0},
        {"id": "1", "model": "WDC WD40EFRX", "serial": "WD-WCC4E1234567",
         "media": 3, "bus": 11, "health": 2, "op": [3, 5], "size": 4000787030016, "spindle": 7200},
        {"id": "2", "model": "SanDisk Ultra USB", "serial": "0101abcdef0123456789",
         "media": 99, "bus": 99, "health": 0, "op": [2], "size": 64003876659, "spindle": 0},
    ],
    "disks": [
        {"number": 0, "style": 2, "guid": "{aaa}", "boot": True, "system": True,
         "readonly": False, "partitions": 3, "free_extent": 0, "size": 1000204886016},
        {"number": 1, "style": 1, "guid": None, "boot": False, "system": False,
         "readonly": False, "partitions": 2, "free_extent": 107374182400, "size": 4000787030016},
        {"number": 2, "style": 1, "guid": None, "boot": False, "system": False,
         "readonly": False, "partitions": 1, "free_extent": 0, "size": 64003876659},
    ],
    "parts": [
        {"disk": 1, "partition": 1, "letter": "E", "offset": 1048576, "size": 4000787030016,
         "gpt": None, "mbr": 7, "boot": False, "system": False},
        {"disk": 2, "partition": 1, "letter": "F", "offset": 1048576, "size": 64003876659,
         "gpt": None, "mbr": 11, "boot": False, "system": False},
        {"disk": 0, "partition": 1, "letter": None, "offset": 1048576, "size": 272629760,
         "gpt": "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}", "mbr": None, "boot": False, "system": True},
        {"disk": 0, "partition": 2, "letter": "X", "offset": 290455552, "size": X_CAP,
         "gpt": "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}", "mbr": None, "boot": True, "system": False},
        {"disk": 0, "partition": 3, "letter": "Y", "offset": 537162416128, "size": Y_CAP,
         "gpt": "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}", "mbr": None, "boot": False, "system": False},
    ],
    "volumes": [
        {"letter": "X:", "label": "Games", "fs": "NTFS", "capacity": X_CAP, "free": X_FREE,
         "drive_type": 3, "guid": "\\\\?\\Volume{x}\\"},
        {"letter": "Y:", "label": "Scratch", "fs": "NTFS", "capacity": Y_CAP, "free": Y_FREE,
         "drive_type": 3, "guid": "\\\\?\\Volume{y}\\"},
        {"letter": "Z:", "label": "media", "fs": "NTFS", "capacity": Z_CAP, "free": Z_FREE,
         "drive_type": 4, "guid": "\\\\?\\Volume{z}\\"},
        {"letter": "E:", "label": "Archive", "fs": "NTFS", "capacity": 4000787030016,
         "free": 1234567890123, "drive_type": 3, "guid": "\\\\?\\Volume{e}\\"},
        {"letter": "F:", "label": "USB STICK", "fs": "FAT32", "capacity": 64003876659,
         "free": 32001938329, "drive_type": 2, "guid": "\\\\?\\Volume{f}\\"},
        {"letter": None, "label": None, "fs": None, "capacity": None, "free": None,
         "drive_type": 0, "guid": "\\\\?\\Volume{null}\\"},
    ],
    "netconns": [
        {"local": "Z:", "remote": "\\\\nas\\media", "status": "OK"},
    ],
}


@pytest.fixture()
def machine(monkeypatch):
    monkeypatch.setattr(diskquery, "query", lambda: MACHINE)
    return MACHINE


@pytest.fixture()
def rich(monkeypatch):
    monkeypatch.setattr(diskquery, "query", lambda: RICH)
    return RICH


def _table(fixture, **args) -> dict:
    import hermes_windows_disks.tools as t
    import hermes_windows_disks.diskquery as q
    original = q.query
    q.query = lambda: fixture
    try:
        return json.loads(t.win_disk_table(args))
    finally:
        q.query = original


def _detail(fixture, **args) -> dict:
    import hermes_windows_disks.tools as t
    import hermes_windows_disks.diskquery as q
    original = q.query
    q.query = lambda: fixture
    try:
        return json.loads(t.win_disk_detail(args))
    finally:
        q.query = original


# --- the enum decoders --------------------------------------------------------

def test_enum_words_from_the_real_machine():
    assert enums.decode(enums.MEDIA_TYPE, 4) == "ssd"
    assert enums.decode(enums.BUS_TYPE, 17) == "nvme"
    assert enums.decode(enums.HEALTH_STATUS, 0) == "unknown"
    assert enums.decode_list(enums.OPERATIONAL_STATUS, [2]) == ["ok"]
    assert enums.decode(enums.DRIVE_TYPE, 4) == "network"
    assert enums.decode(enums.PARTITION_STYLE, 2) == "gpt"
    assert enums.decode(enums.PARTITION_STYLE, 1) == "mbr"


def test_unknown_enum_numbers_say_so_instead_of_guessing():
    assert enums.decode(enums.BUS_TYPE, 99) == "unknown(99)"
    assert enums.decode(enums.MEDIA_TYPE, None) == "unknown(None)"
    assert enums.decode_list(enums.OPERATIONAL_STATUS, 3) == ["degraded"]  # unwrapped scalar
    assert enums.decode_list(enums.OPERATIONAL_STATUS, None) == []


def test_partition_kind_from_the_guid_and_the_mbr_byte():
    assert enums.partition_kind("{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}", None) == "efi system"
    assert enums.partition_kind("{de94bba4-06d1-4d40-a16a-bfd50179d6ac}", None) == "windows recovery"
    assert enums.partition_kind(None, 7).startswith("installable")
    assert enums.partition_kind(None, 11) == "fat32"
    assert enums.partition_kind("{11111111-2222-3333-4444-555555555555}", None) == \
        "{11111111-2222-3333-4444-555555555555}"


# --- the table ----------------------------------------------------------------

def test_table_lists_the_disk_and_lettered_volumes_and_hides_the_rest(machine):
    out = json.loads(tools.win_disk_table({}))
    assert out["ok"] is True
    kinds = [(row["kind"], row.get("drive")) for row in out["rows"]]
    assert ("volume", "C:") in kinds and ("volume", "D:") in kinds
    letters = {drive for kind, drive in kinds if kind == "volume"}
    assert all(drive for drive in letters)  # no letterless row while hidden
    disk_row = next(row for row in out["rows"] if row["kind"] == "disk")
    assert disk_row["model"] == "UMIS RPJYJ1T24RLS1QWY"
    assert disk_row["media"] == "ssd" and disk_row["bus"] == "nvme"
    assert any("2 volume(s) without a drive letter hidden" in note for note in out["notes"])


def test_table_include_letterless_shows_winre_and_efi(machine):
    out = json.loads(tools.win_disk_table({"include_letterless": True}))
    labels = {row.get("label") for row in out["rows"] if row["kind"] == "volume"}
    assert {"Windows-SSD", "Data", "WINRE_DRV", "SYSTEM_DRV"} <= labels


def test_table_kind_and_query_filters(machine):
    disks_only = json.loads(tools.win_disk_table({"kind": "disk"}))
    assert {row["kind"] for row in disks_only["rows"]} == {"disk"}
    vols_only = json.loads(tools.win_disk_table({"kind": "volume"}))
    assert {row["kind"] for row in vols_only["rows"]} == {"volume"}
    by_query = json.loads(tools.win_disk_table({"query": "umis"}))
    assert {row["kind"] for row in by_query["rows"]} == {"disk"}
    by_letter = json.loads(tools.win_disk_table({"query": "d:"}))
    assert [row.get("drive") for row in by_letter["rows"]] == ["D:"]


def test_table_links_each_volume_to_its_disk(machine):
    out = json.loads(tools.win_disk_table({}))
    c = next(row for row in out["rows"] if row.get("drive") == "C:")
    assert c["disk"] == 0
    assert c["filesystem"] == "NTFS" and c["drive_type"] == "fixed"


def test_table_health_notes_unknown_and_warning(rich):
    out = _table(RICH)
    joined = " ".join(out["notes"])
    assert "reports warning - back up" in joined  # the WDC disk
    assert "unknown(99)" in json.dumps(out)  # the USB stick's unseen enum values


def test_table_low_free_space_note_lists_the_tight_volumes(rich):
    out = _table(RICH)
    joined = " ".join(out["notes"])
    assert "low free space: X: 9.4% free; Y: 4.2% free" in joined


def test_table_volume_verdicts_and_unc(rich):
    out = _table(RICH)
    by_drive = {row.get("drive"): row for row in out["rows"] if row["kind"] == "volume"}
    assert by_drive["X:"]["free_verdict"] == "low"
    assert by_drive["Y:"]["free_verdict"] == "critical"
    assert by_drive["Z:"]["free_verdict"] == "fine"
    assert by_drive["Z:"]["drive_type"] == "network"
    assert by_drive["Z:"]["unc"] == "\\\\nas\\media"
    assert by_drive["F:"]["drive_type"] == "removable"
    assert by_drive["Z:"]["disk"] is None  # a mapped drive hangs off no local disk


def test_free_verdict_thresholds():
    assert tools._free_verdict(4.9) == "critical"
    assert tools._free_verdict(5.0) == "low"
    assert tools._free_verdict(9.9) == "low"
    assert tools._free_verdict(10.0) == "fine"
    assert tools._free_verdict(None) == "unknown"


def test_free_pct_survives_a_missing_capacity():
    assert tools._pct(100, 0) is None
    assert tools._pct(None, 100) is None
    assert tools._pct(50, 200) == 25.0


def test_single_object_answers_are_unwrapped_before_parsing(machine):
    # PowerShell does not wrap a one-element array: every listing may arrive as a
    # bare object, and the parse layer normalizes all of them
    bare = {key: (value[0] if isinstance(value, list) and value else value)
            for key, value in MACHINE.items()}
    out = _table(bare)
    assert out["ok"] is True
    assert any(row["kind"] == "disk" for row in out["rows"])
    assert any(row.get("drive") == "C:" for row in out["rows"])


# --- the detail ---------------------------------------------------------------

def test_detail_by_letter_with_or_without_the_colon(machine):
    for target in ("C:", "c"):
        out = _detail(MACHINE, target=target)
        assert out["matched"] == "volume"
        assert out["volume"]["drive"] == "C:"
        assert out["free_space"].startswith("69.5% free")


def test_detail_by_label_finds_the_volume(machine):
    out = _detail(MACHINE, target="Data")
    assert out["matched"] == "volume" and out["volume"]["drive"] == "D:"
    assert out["volume"]["disk"] == 0


def test_detail_by_model_reads_the_disk_with_its_health_sentence(machine):
    out = _detail(MACHINE, target="umis")
    assert out["matched"] == "disk"
    assert "unknown" in out["health"] and "OperationalStatus" in out["health"]
    assert out["disk"]["partition_style"] == "gpt"
    assert out["disk"]["boot"] is True and out["disk"]["system"] is True


def test_detail_disk_layout_decodes_every_partition(machine):
    out = _detail(MACHINE, target="0")
    layout = [(p["partition"], p["type"], p["letter"]) for p in out["partitions"]]
    assert layout == [
        (1, "efi system", None),
        (2, "microsoft reserved", None),
        (3, "basic data", "C:"),
        (4, "basic data", "D:"),
        (5, "windows recovery", None),
    ]
    drives = {v["drive"] for v in out["volumes"]}
    assert drives == {"C:", "D:"}


def test_detail_by_serial_and_by_disk_number_words(rich):
    by_serial = _detail(RICH, target="WD-WCC4E")
    assert by_serial["matched"] == "disk" and by_serial["disk"]["model"] == "WDC WD40EFRX"
    assert "warning" in by_serial["health"]
    for target in ("1", "disk 2"):
        out = _detail(RICH, target=target)
        assert out["matched"] == "disk"


def test_detail_ambiguous_model_names_the_others(rich):
    # 'sa' sits at the front of two models (Samsung, SanDisk) and in no serial, so
    # the model tier answers with the first disk and a note naming the other
    out = _detail(RICH, target="sa")
    assert out["matched"] == "disk" and out["disk"]["model"] == "Samsung SSD 990 PRO"
    joined = " ".join(out["notes"])
    assert "2 disks match 'sa'" in joined and "name it by serial or number" in joined


def test_detail_mbr_disk_reports_spindle_and_free_extent(rich):
    out = _detail(RICH, target="WDC")
    joined = " ".join(out["notes"])
    assert "spindle 7200 rpm" in joined
    assert "largest contiguous free extent" in joined
    assert out["partitions"][0]["type"].startswith("installable")


def test_detail_solid_state_says_no_spindle(machine):
    out = _detail(MACHINE, target="UMIS")
    assert any("no spindle" in note for note in out["notes"])


def test_detail_network_volume_names_the_unc(rich):
    out = _detail(RICH, target="Z:")
    assert out["matched"] == "volume"
    joined = " ".join(out["notes"])
    assert "\\\\nas\\media" in joined and "network volume" in joined


def test_detail_volume_points_at_the_owning_disk(rich):
    out = _detail(RICH, target="X:")
    joined = " ".join(out["notes"])
    assert "the owning disk (disk 0, Samsung SSD 990 PRO)" in joined


def test_detail_nothing_matched_and_no_target(machine):
    out = _detail(MACHINE, target="Quantum Fireball")
    assert out["ok"] is False and out["code"] == "nothing_matched"
    missing = json.loads(tools.win_disk_detail({}))
    assert missing["ok"] is False and missing["code"] == "usage"


def test_powershell_failure_answers_ok_false(machine, monkeypatch):
    def boom():
        raise diskquery.PowerShellError("the storage query failed: boom")
    monkeypatch.setattr(diskquery, "query", boom)
    table = json.loads(tools.win_disk_table({}))
    detail = json.loads(tools.win_disk_detail({"target": "C:"}))
    assert table["ok"] is False and table["code"] == "disks_unavailable"
    assert detail["ok"] is False and detail["code"] == "disks_unavailable"
