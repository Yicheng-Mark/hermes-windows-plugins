"""The same two tools against this machine's real adapters (read-only)."""

from __future__ import annotations

import json
import sys

import pytest

from hermes_windows_network import netpowershell, tools

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="network adapters are Windows only")


def test_the_cmdlets_answer_with_adapters() -> None:
    rows = netpowershell.adapters()
    assert rows, "a Windows machine has network adapters"
    for row in rows:
        assert isinstance(row.get("if_index"), int)
        assert str(row.get("status"))  # enum names, not localized words
        assert row.get("name")  # localized data, carried as data


def test_the_listing_reads_this_machines_adapters() -> None:
    result = json.loads(tools.win_adapter_table({}))
    assert result["ok"] is True, result
    assert result["visible"] >= 1
    for row in result["adapters"]:
        assert row["state"] in tools.KNOWN_STATES | {"unknown"}
        assert "problem" in row
        if row["state"] == "up":
            assert row["problem"] is None


def test_ghosts_are_hidden_until_asked_for() -> None:
    visible = json.loads(tools.win_adapter_table({}))
    every = json.loads(tools.win_adapter_table({"include_absent": True}))
    assert every["visible"] >= visible["visible"]
    assert all(row["state"] != "not present" for row in visible["adapters"])


def test_an_up_adapter_details_with_its_addresses() -> None:
    listing = json.loads(tools.win_adapter_table({}))
    up = [row for row in listing["adapters"] if row["state"] == "up"]
    if not up:
        pytest.skip("no adapter is up on this machine right now")
    detail = json.loads(tools.win_adapter_detail({"name": up[0]["name"]}))
    assert detail["ok"] is True, detail
    assert detail["ip"] is not None
    addresses = detail["ip"]["ipv4"]
    assert all("prefix" in row and "origin" in row for row in addresses)
    assert detail["notes"]  # a verdict was reached, not silence
    # the diagnosis and the facts agree: a link-local-only adapter never counts as connected
    if addresses and all(row["link_local"] for row in addresses):
        assert not any(note.startswith("connected") for note in detail["notes"])


def test_every_visible_adapter_can_be_detailed() -> None:
    listing = json.loads(tools.win_adapter_table({"limit": 8}))
    for row in listing["adapters"]:
        detail = json.loads(tools.win_adapter_detail({"name": row["name"]}))
        assert detail["ok"] is True, detail
        assert detail["state"] == row["state"]
        assert isinstance(detail["notes"], list)
