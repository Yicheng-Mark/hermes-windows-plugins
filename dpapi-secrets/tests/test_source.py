from pathlib import Path

import pytest

pytest.importorskip(
    "agent.secret_sources.base",
    reason="Hermes core is not installed; the catalog validator checks the real contract",
)

from agent.secret_sources.base import ErrorKind  # noqa: E402

from hermes_dpapi_secrets import dpapi, store  # noqa: E402
from hermes_dpapi_secrets.source import DpapiSecretsSource  # noqa: E402

HOME = Path(".")


@pytest.fixture
def fake_dpapi(monkeypatch):
    def protect(data: bytes) -> bytes:
        return b"fake:" + bytes(byte ^ 0x5A for byte in data)

    def unprotect(blob: bytes) -> bytes:
        if not blob.startswith(b"fake:"):
            raise dpapi.DpapiError("CryptUnprotectData", 13)
        return bytes(byte ^ 0x5A for byte in blob[5:])

    monkeypatch.setattr(dpapi, "protect", protect)
    monkeypatch.setattr(dpapi, "unprotect", unprotect)
    monkeypatch.setattr(dpapi, "available", lambda: True)


def _source():
    return DpapiSecretsSource()


def _store(tmp_path, values):
    store.write_store(tmp_path / "secrets.dpapi", values)


def test_resolves_mapped_entries(tmp_path, fake_dpapi):
    _store(tmp_path, {"openai": "sk-a", "zai": "sk-b"})
    result = _source().fetch(
        {"map": {"OPENAI_API_KEY": "openai", "ZAI_API_KEY": "dpapi://zai"}}, tmp_path
    )
    assert result.ok
    assert result.secrets == {"OPENAI_API_KEY": "sk-a", "ZAI_API_KEY": "sk-b"}
    assert result.warnings == []


def test_honours_a_custom_file(tmp_path, fake_dpapi):
    other = tmp_path / "elsewhere.dpapi"
    store.write_store(other, {"openai": "sk-a"})
    result = _source().fetch({"file": "elsewhere.dpapi", "map": {"K": "openai"}}, tmp_path)
    assert result.secrets == {"K": "sk-a"}


def test_missing_entry_is_a_warning_and_the_rest_still_resolve(tmp_path, fake_dpapi):
    _store(tmp_path, {"openai": "sk-a"})
    result = _source().fetch(
        {"map": {"A": "openai", "B": "absent"}}, tmp_path
    )
    assert result.ok
    assert result.secrets == {"A": "sk-a"}
    assert any("absent" in warning for warning in result.warnings)


def test_every_entry_missing_is_an_error_not_a_crash(tmp_path, fake_dpapi):
    _store(tmp_path, {"openai": "sk-a"})
    result = _source().fetch({"map": {"B": "absent"}}, tmp_path)
    assert not result.ok
    assert result.error_kind is ErrorKind.EMPTY_VALUE
    assert result.secrets == {}


def test_an_empty_entry_is_skipped(tmp_path, fake_dpapi):
    _store(tmp_path, {"openai": ""})
    result = _source().fetch({"map": {"A": "openai"}}, tmp_path)
    assert result.error_kind is ErrorKind.EMPTY_VALUE
    assert any("empty" in warning for warning in result.warnings)


def test_absent_store_is_not_configured(tmp_path, fake_dpapi):
    result = _source().fetch({"map": {"A": "openai"}}, tmp_path)
    assert result.error_kind is ErrorKind.NOT_CONFIGURED
    assert not result.secrets


def test_a_foreign_file_is_not_configured(tmp_path, fake_dpapi):
    (tmp_path / "secrets.dpapi").write_bytes(b"not a store")
    result = _source().fetch({"map": {"A": "openai"}}, tmp_path)
    assert result.error_kind is ErrorKind.NOT_CONFIGURED


def test_undecryptable_store_is_an_auth_failure(tmp_path, fake_dpapi, monkeypatch):
    _store(tmp_path, {"openai": "sk-a"})

    def fail(blob):
        raise dpapi.DpapiError("CryptUnprotectData", 13)

    monkeypatch.setattr(dpapi, "unprotect", fail)
    result = _source().fetch({"map": {"A": "openai"}}, tmp_path)
    assert result.error_kind is ErrorKind.AUTH_FAILED
    assert not result.secrets


def test_non_windows_is_a_binary_missing_error(tmp_path, fake_dpapi, monkeypatch):
    _store(tmp_path, {"openai": "sk-a"})
    monkeypatch.setattr(dpapi, "available", lambda: False)
    result = _source().fetch({"map": {"A": "openai"}}, tmp_path)
    assert result.error_kind is ErrorKind.BINARY_MISSING


def test_unexpected_failure_never_escapes_fetch(tmp_path, fake_dpapi, monkeypatch):
    _store(tmp_path, {"openai": "sk-a"})

    def boom(path):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(store, "read_store", boom)
    result = _source().fetch({"map": {"A": "openai"}}, tmp_path)
    assert result.error_kind is ErrorKind.INTERNAL
    assert not result.secrets


def test_malformed_sections_never_raise(tmp_path, fake_dpapi):
    for cfg in ({}, {"enabled": True}, {"map": "nope"}, {"map": {}}, None):
        result = _source().fetch(cfg if isinstance(cfg, dict) else {}, tmp_path)
        assert result.error_kind is ErrorKind.NOT_CONFIGURED


def test_identity():
    source = _source()
    assert source.name == "dpapi"
    assert source.shape == "mapped"
    assert source.scheme == "dpapi"
    assert source.is_enabled({}) is False
    assert source.is_enabled({"enabled": True}) is True


def test_remediation_points_at_the_cli():
    source = _source()
    hint = source.remediation(ErrorKind.NOT_CONFIGURED, {})
    assert "hermes_dpapi_secrets" in hint
