"""The cmdlet calls and their answers (hermes_windows_network/netpowershell.py)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from hermes_windows_network import netpowershell


class Finished:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_one_adapter_comes_back_as_a_one_row_list(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = json.dumps({"name": "WLAN", "status": "Up"}).encode()
    monkeypatch.setattr(netpowershell.subprocess, "run", lambda *a, **k: Finished(answer))
    assert netpowershell.adapters() == [{"name": "WLAN", "status": "Up"}]


def test_a_byte_order_mark_does_not_hide_the_json(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = b"\xef\xbb\xbf" + json.dumps([{"name": "WLAN"}]).encode()
    monkeypatch.setattr(netpowershell.subprocess, "run", lambda *a, **k: Finished(answer))
    assert netpowershell.adapters() == [{"name": "WLAN"}]


def test_a_failed_powershell_is_an_error_with_its_complaint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_a: Any, **_k: Any) -> Finished:
        # a complaint in the machine's own words (GBK on a Chinese Windows), not English
        return Finished(stderr="Get-NetAdapter : 找不到".encode("gbk"), returncode=1)

    monkeypatch.setattr(netpowershell.subprocess, "run", fail)
    with pytest.raises(netpowershell.PowerShellError) as caught:
        netpowershell.adapters()
    assert "exited 1" in str(caught.value)


def test_silence_and_a_slow_answer_are_both_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netpowershell.subprocess, "run", lambda *a, **k: Finished())
    with pytest.raises(netpowershell.PowerShellError):
        netpowershell.adapters()

    def slow(*_a: Any, **_k: Any) -> Finished:
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=1)

    monkeypatch.setattr(netpowershell.subprocess, "run", slow)
    with pytest.raises(netpowershell.PowerShellError) as caught:
        netpowershell.adapters()
    assert "did not answer" in str(caught.value)


def test_an_answer_that_is_not_json_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        netpowershell.subprocess, "run", lambda *a, **k: Finished(b"WARNING: something")
    )
    with pytest.raises(netpowershell.PowerShellError) as caught:
        netpowershell.adapters()
    assert "not JSON" in str(caught.value)


def test_a_missing_powershell_is_reported_as_such(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*_a: Any, **_k: Any) -> Finished:
        raise FileNotFoundError("powershell.exe")

    monkeypatch.setattr(netpowershell.subprocess, "run", missing)
    with pytest.raises(netpowershell.PowerShellError) as caught:
        netpowershell.adapters()
    assert "not on PATH" in str(caught.value)


def test_an_answer_that_is_neither_list_nor_dict_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        netpowershell.subprocess, "run", lambda *a, **k: Finished(b'"just a string"')
    )
    with pytest.raises(netpowershell.PowerShellError) as caught:
        netpowershell.adapters()
    assert "expected a list" in str(caught.value)


def test_the_configuration_script_carries_the_interface_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_run(script: str, timeout: float = 0) -> Any:
        seen.append(script)
        return {"found": False, "ipv4": []}

    monkeypatch.setattr(netpowershell, "run", fake_run)
    answer = netpowershell.configuration(47)
    assert answer == {
        "found": False,
        "ipv4": [],
        "ipv6": [],
        "dns4": [],
        "dns6": [],
    }
    assert "$idx = 47" in seen[0]
    assert "Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object" in seen[0]


def test_an_index_that_is_not_one_is_refused() -> None:
    with pytest.raises(netpowershell.PowerShellError):
        netpowershell.configuration("14; Remove-Item")  # type: ignore[arg-type]
    with pytest.raises(netpowershell.PowerShellError):
        netpowershell.configuration(-1)


def test_an_unwrapped_list_is_read_as_the_list_it_meant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a live run on Windows PowerShell 5.1 answered with the one address as a bare
    # object and the empty ones as {} -- the normalisation turns them back into lists
    unwrapped = {
        "if_index": 14,
        "found": True,
        "ipv4": {"address": "192.168.0.200", "prefix": 24, "origin": "Dhcp"},
        "ipv6": {},
        "gateway4": "192.168.0.1",
        "gateway6": None,
        "dns4": "223.5.5.5",
        "dns6": {},
    }
    monkeypatch.setattr(netpowershell, "run", lambda script, timeout=0: unwrapped)
    answer = netpowershell.configuration(14)
    assert answer["ipv4"] == [{"address": "192.168.0.200", "prefix": 24, "origin": "Dhcp"}]
    assert answer["ipv6"] == []
    assert answer["dns4"] == ["223.5.5.5"]
    assert answer["dns6"] == []
