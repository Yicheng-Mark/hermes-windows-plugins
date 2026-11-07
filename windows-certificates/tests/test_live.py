"""Live tests: the real certificate stores of this machine, unelevated."""

from __future__ import annotations

import json
import re
import time

import pytest

from hermes_windows_certificates import certstore, tools

win32_only = pytest.mark.skipif(certstore.available() is False,
                                reason="the Windows certificate stores are Windows-only")

HEX40 = re.compile(r"^[0-9A-F]{40}$")


@win32_only
class TestWalker:
    def test_user_root_store_walks_with_complete_rows(self):
        rows = certstore.iter_certs(contexts=["user"], stores=["Root"])
        assert len(rows) >= 5  # every real Windows carries dozens of roots
        for row in rows[:10]:
            assert isinstance(row["subject"], str) and row["subject"]
            assert HEX40.match(row["thumbprint"] or "")
            assert row["not_before"] and row["not_after"]
            assert row["store"] == "Root" and row["context"] == "user"
            assert row["signature_oid"]  # every certificate states how it was signed

    def test_self_signed_roots_exist(self):
        rows = certstore.iter_certs(contexts=["user"], stores=["Root"])
        assert any(row["self_signed"] for row in rows)  # a root signs itself

    def test_full_default_walk_is_fast_enough(self):
        started = time.perf_counter()
        rows = certstore.iter_certs()
        elapsed = time.perf_counter() - started
        print(f"\nfull walk: {len(rows)} certificates in {elapsed * 1000:.0f} ms")
        assert len(rows) >= 30  # user + machine, MY/Root/CA, a real machine's load
        assert elapsed < 3.0

    def test_machines_intermediate_store_answers_unelevated(self):
        rows = certstore.iter_certs(contexts=["machine"], stores=["CA"])
        assert isinstance(rows, list)  # readable without elevation; may be empty


@win32_only
class TestToolsEndToEnd:
    def test_table_on_the_real_stores(self):
        payload = json.loads(tools.win_cert_table({}))
        assert payload["ok"] is True, payload
        rows = payload["certificates"]
        assert rows
        states = {row["state"] for row in rows}
        assert states <= {"expired", "expiring", "valid", "not_yet_valid", "unknown"}
        # the sort contract: the first row is never 'valid' while a troubled one exists
        if states - {"valid"}:
            assert rows[0]["state"] != "valid"
        print(f"\ntable: {len(rows)} rows, states={sorted(states)}, "
              f"notes={payload['notes']}")

    def test_detail_by_a_real_thumbprint(self):
        rows = certstore.iter_certs(contexts=["user"], stores=["Root"])
        target = rows[0]
        payload = json.loads(tools.win_cert_detail({"thumbprint": target["thumbprint"]}))
        assert payload["ok"] is True, payload
        cert = payload["certificate"]
        assert cert["thumbprint"] == target["thumbprint"]
        assert cert["subject"] == target["subject"]
        assert cert["validity"]["note"]
        assert cert["signature_algorithm"]["oid"]

    def test_detail_survives_three_real_certificates(self):
        rows = certstore.iter_certs()[:3]
        for row in rows:
            payload = json.loads(tools.win_cert_detail({"thumbprint": row["thumbprint"]}))
            assert payload["ok"] is True
            key = payload["certificate"]["public_key"]
            if key["algorithm"]["name"] == "RSA":
                assert key["bits"] and key["bits"] % 256 == 0

    def test_expired_only_or_empty_notes_say_so(self):
        payload = json.loads(tools.win_cert_table({"expired_only": True}))
        assert payload["ok"] is True
        for row in payload["certificates"]:
            assert row["state"] in ("expired", "expiring", "not_yet_valid", "unknown")
