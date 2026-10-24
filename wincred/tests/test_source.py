from pathlib import Path

import pytest

pytest.importorskip(
    "agent.secret_sources.base",
    reason="Hermes core is not installed; the catalog validator checks the real contract",
)

from agent.secret_sources.base import ErrorKind  # noqa: E402

from hermes_wincred import credman  # noqa: E402
from hermes_wincred.source import WinCredSource  # noqa: E402

HOME = Path(".")


def _source():
    return WinCredSource()


def _available(monkeypatch, blobs):
    monkeypatch.setattr(credman, "available", lambda: True)

    def read(target):
        value = blobs[target]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(credman, "read_generic", read)


def test_resolves_mapped_credentials(monkeypatch):
    _available(monkeypatch, {"hermes/a": b"sk-a", "hermes/b": "sk-b".encode("utf-16-le")})
    result = _source().fetch(
        {"map": {"A_KEY": "hermes/a", "B_KEY": "wincred://hermes/b"}}, HOME
    )
    assert result.ok
    assert result.secrets == {"A_KEY": "sk-a", "B_KEY": "sk-b"}
    assert result.warnings == []


def test_missing_credential_is_a_warning_and_others_still_resolve(monkeypatch):
    _available(monkeypatch, {
        "hermes/a": b"sk-a",
        "hermes/missing": credman.CredManError("hermes/missing", credman.ERROR_NOT_FOUND),
    })
    result = _source().fetch(
        {"map": {"A_KEY": "hermes/a", "MISSING_KEY": "hermes/missing"}}, HOME
    )
    assert result.ok
    assert result.secrets == {"A_KEY": "sk-a"}
    assert any("hermes/missing" in w and "no generic credential" in w
               for w in result.warnings)


def test_all_reads_failing_is_an_error_not_an_exception(monkeypatch):
    _available(monkeypatch, {
        "hermes/missing": credman.CredManError("hermes/missing", credman.ERROR_NOT_FOUND),
    })
    result = _source().fetch({"map": {"MISSING_KEY": "hermes/missing"}}, HOME)
    assert not result.ok
    assert result.error_kind is ErrorKind.EMPTY_VALUE
    assert result.secrets == {}


def test_access_denied_and_unknown_errors_are_reported(monkeypatch):
    _available(monkeypatch, {
        "hermes/denied": credman.CredManError("hermes/denied", credman.ERROR_ACCESS_DENIED),
        "hermes/other": credman.CredManError("hermes/other", 87),
    })
    result = _source().fetch(
        {"map": {"DENIED": "hermes/denied", "OTHER": "hermes/other"}}, HOME
    )
    assert not result.ok
    assert any("access denied" in w for w in result.warnings)
    assert any("winerror 87" in w for w in result.warnings)


def test_off_windows_is_binary_missing(monkeypatch):
    monkeypatch.setattr(credman, "available", lambda: False)
    result = _source().fetch({"map": {"A_KEY": "hermes/a"}}, HOME)
    assert not result.ok
    assert result.error_kind is ErrorKind.BINARY_MISSING


def test_empty_mapping_is_not_configured(monkeypatch):
    for cfg in ({}, {"map": {}}, {"map": {"bad name": "x"}}, None, [], "x"):
        result = _source().fetch(cfg, HOME)
        assert not result.ok
        assert result.error_kind is ErrorKind.NOT_CONFIGURED


def test_undecodable_blob_is_a_warning(monkeypatch):
    _available(monkeypatch, {"hermes/bin": b"\xff\x00\xfe"})
    result = _source().fetch({"map": {"BIN": "hermes/bin"}}, HOME)
    assert not result.ok
    assert any("not UTF-8 or UTF-16" in w for w in result.warnings)


def test_empty_secret_is_a_warning(monkeypatch):
    _available(monkeypatch, {"hermes/empty": b""})
    result = _source().fetch({"map": {"EMPTY": "hermes/empty"}}, HOME)
    assert not result.ok
    assert any("is empty" in w for w in result.warnings)


def test_unexpected_exception_never_escapes(monkeypatch):
    _available(monkeypatch, {"hermes/boom": RuntimeError("kaboom")})
    result = _source().fetch({"map": {"BOOM": "hermes/boom"}}, HOME)
    assert not result.ok
    assert any("unexpectedly" in w for w in result.warnings)


def test_values_are_never_echoed_in_warnings(monkeypatch):
    _available(monkeypatch, {"hermes/a": b"sk-supersecret"})
    result = _source().fetch({"map": {"A_KEY": "hermes/a"}}, HOME)
    assert result.secrets["A_KEY"] == "sk-supersecret"
    assert not any("sk-supersecret" in w for w in result.warnings)


def test_fetch_returns_a_fetch_result_with_warnings_on_malformed_config(monkeypatch):
    _available(monkeypatch, {})
    result = _source().fetch({"map": {"not an env name": "x", "OK": ""}}, HOME)
    assert result.warnings
    assert result.error is not None
