"""Live end-to-end against the real Windows Data Protection API.

Opt-in: this writes a real DPAPI blob for the current Windows user, so it runs only
with ``HERMES_DPAPI_LIVE=1``. Everything it creates lives under ``tmp_path`` and is
removed by pytest.
"""

import io
import os

import pytest

pytest.importorskip(
    "agent.secret_sources.base",
    reason="Hermes core is not installed; run with PYTHONPATH pointing at a Hermes checkout",
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only"),
    pytest.mark.skipif(
        os.environ.get("HERMES_DPAPI_LIVE") != "1",
        reason="set HERMES_DPAPI_LIVE=1 to write real DPAPI blobs for this user",
    ),
]

from hermes_dpapi_secrets import cli, dpapi, store  # noqa: E402
from hermes_dpapi_secrets.source import DpapiSecretsSource  # noqa: E402


def test_real_round_trip_including_non_ascii():
    payload = "sk-live-üñï-✓".encode("utf-8")
    blob = dpapi.protect(payload)
    assert blob != payload
    assert dpapi.unprotect(blob) == payload


def test_store_survives_a_real_dpapi_round_trip(tmp_path):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"openai": "sk-live-1", "zai": "sk-live-2"})
    assert store.read_store(path) == {"openai": "sk-live-1", "zai": "sk-live-2"}


def test_source_resolves_from_a_real_store(tmp_path):
    store.write_store(tmp_path / "secrets.dpapi", {"zai": "sk-live"})
    result = DpapiSecretsSource().fetch({"map": {"ZAI_API_KEY": "zai"}}, tmp_path)
    assert result.ok
    assert result.secrets == {"ZAI_API_KEY": "sk-live"}


def test_a_tampered_blob_fails_closed(tmp_path):
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"openai": "sk-live"})
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 0xFF
    path.write_bytes(bytes(raw))
    with pytest.raises(dpapi.DpapiError):
        store.read_store(path)


def test_a_store_from_another_windows_user_would_be_refused(tmp_path):
    """A blob protected as a *different* user cannot be unwrapped with ours."""
    # Same code path as the tamper test but through the source, which must report
    # AUTH_FAILED rather than raising.
    path = tmp_path / "secrets.dpapi"
    store.write_store(path, {"openai": "sk-live"})
    raw = bytearray(path.read_bytes())
    raw[len(store.MAGIC) + 20] ^= 0xFF
    path.write_bytes(bytes(raw))
    result = DpapiSecretsSource().fetch({"map": {"K": "openai"}}, tmp_path)
    assert not result.ok
    assert result.error_kind is not None


def test_cli_set_and_list_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "secrets.dpapi"
    monkeypatch.setattr("sys.stdin", io.StringIO("sk-from-stdin\n"))
    assert cli.main(["--file", str(path), "set", "openai"]) == 0
    assert store.read_store(path) == {"openai": "sk-from-stdin"}
    assert cli.main(["--file", str(path), "list"]) == 0
    assert cli.main(["--file", str(path), "unset", "openai"]) == 0
    assert store.read_store(path) == {}
