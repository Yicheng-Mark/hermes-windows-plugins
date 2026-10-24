import json

import pytest

from hermes_dpapi_secrets import dpapi, store


@pytest.fixture
def fake_dpapi(monkeypatch):
    """Reversible stand-in for DPAPI so the store tests run on any platform."""
    def protect(data: bytes) -> bytes:
        return b"fake:" + bytes(byte ^ 0x5A for byte in data)

    def unprotect(blob: bytes) -> bytes:
        if not blob.startswith(b"fake:"):
            raise dpapi.DpapiError("CryptUnprotectData", 13)
        return bytes(byte ^ 0x5A for byte in blob[5:])

    monkeypatch.setattr(dpapi, "protect", protect)
    monkeypatch.setattr(dpapi, "unprotect", unprotect)
    return protect


def test_round_trip(tmp_path, fake_dpapi):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"openai": "sk-1", "zai": "sk-2"})
    assert store.read_store(path) == {"openai": "sk-1", "zai": "sk-2"}


def test_file_starts_with_the_magic_and_hides_the_plaintext(tmp_path, fake_dpapi):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"openai": "sk-super-secret"})
    raw = path.read_bytes()
    assert raw.startswith(store.MAGIC)
    # The fake cipher is reversible, but the real point is that the value is not
    # stored verbatim beside the header.
    assert b"sk-super-secret" not in raw


def test_entry_names_are_sorted_and_values_never_returned(tmp_path, fake_dpapi):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"b": "2", "a": "1"})
    assert store.store_entries(path) == ["a", "b"]


def test_rejects_a_foreign_file(tmp_path, fake_dpapi):
    path = tmp_path / "secrets.dpapi"
    path.write_bytes(b'{"openai": "sk-1"}')
    with pytest.raises(store.StoreFormatError):
        store.read_store(path)


def test_rejects_a_header_without_payload(tmp_path, fake_dpapi):
    path = tmp_path / "secrets.dpapi"
    path.write_bytes(store.MAGIC)
    with pytest.raises(store.StoreFormatError):
        store.read_store(path)


def test_rejects_a_payload_that_is_not_a_string_map(tmp_path, fake_dpapi, monkeypatch):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"a": "1"})
    monkeypatch.setattr(dpapi, "unprotect", lambda blob: json.dumps({"a": 1}).encode())
    with pytest.raises(store.StoreFormatError):
        store.read_store(path)


def test_rejects_a_payload_that_is_not_json(tmp_path, fake_dpapi, monkeypatch):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"a": "1"})
    monkeypatch.setattr(dpapi, "unprotect", lambda blob: b"\xff\xfe not json")
    with pytest.raises(store.StoreFormatError):
        store.read_store(path)


def test_undecryptable_blob_surfaces_the_dpapi_error(tmp_path, fake_dpapi, monkeypatch):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"a": "1"})

    def fail(blob):
        raise dpapi.DpapiError("CryptUnprotectData", 13)

    monkeypatch.setattr(dpapi, "unprotect", fail)
    with pytest.raises(dpapi.DpapiError):
        store.read_store(path)


def test_a_failed_write_leaves_the_previous_store_intact(tmp_path, fake_dpapi, monkeypatch):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"a": "1"})

    def explode(data):
        raise RuntimeError("boom")

    monkeypatch.setattr(dpapi, "protect", explode)
    with pytest.raises(RuntimeError):
        store.write_store(path, {"a": "2"})

    monkeypatch.setattr(dpapi, "protect", fake_dpapi)
    assert store.read_store(path) == {"a": "1"}
    assert list(tmp_path.iterdir()) == [path], "no temp file may survive a failed write"


def test_write_creates_missing_directories(tmp_path, fake_dpapi):
    path = tmp_path / "nested" / "dir" / "secrets.dpapi"
    store.write_store(path, {"a": "1"})
    assert store.read_store(path) == {"a": "1"}
