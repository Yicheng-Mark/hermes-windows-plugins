"""Unit tests: every layer with fakes - no crypt32, no live stores."""

from __future__ import annotations

import json
import re
from datetime import datetime

import pytest

from hermes_windows_certificates import certstore, oids, tools

NOW = 1_800_000_000.0
DAY = 86400


# --- FILETIME ---------------------------------------------------------------

def test_filetime_roundtrip_and_zero():
    epoch = 1735689600.0  # 2025-01-01T00:00:00Z
    raw = int(epoch * 10_000_000) + 116444736000000000
    assert certstore.filetime_to_epoch(raw & 0xFFFFFFFF, raw >> 32) == epoch
    assert certstore.filetime_to_epoch(0, 0) is None  # the zero stamp means "unset"


# --- the DER helpers --------------------------------------------------------

def _rsa_der(modulus: bytes) -> bytes:
    # SEQUENCE { INTEGER modulus, INTEGER 65537 }
    def der_len(n: int) -> bytes:
        if n < 0x80:
            return bytes([n])
        body = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return bytes([0x80 | len(body)]) + body

    parts = b"\x02" + der_len(len(modulus)) + modulus
    parts += b"\x02\x03\x01\x00\x01"
    return b"\x30" + der_len(len(parts)) + parts


def test_rsa_bit_length_reads_the_modulus():
    modulus = b"\xf0" + b"\x11" * 255  # 256 bytes, top bit set: a 2048-bit key
    assert oids.rsa_bit_length(_rsa_der(modulus)) == 2048
    # DER adds a leading zero to keep the sign bit clear; it is not a key bit
    assert oids.rsa_bit_length(_rsa_der(b"\x00" + modulus)) == 2048
    short = b"\xa0" + b"\x7f" * 127  # 128 bytes: a 1024-bit key
    assert oids.rsa_bit_length(_rsa_der(short)) == 1024


def test_rsa_bit_length_rejects_non_sequences():
    assert oids.rsa_bit_length(b"") is None
    assert oids.rsa_bit_length(b"\x02\x01\x00") is None
    assert oids.rsa_bit_length(b"\x30\x10\x02") is None  # length runs off the end


def test_curve_matching_by_oid_content():
    p256 = bytes.fromhex("06082a8648ce3d030107")  # the OID as DER content
    assert oids.curve_of(p256) == "P-256 (secp256r1)"
    assert oids.curve_of(bytes.fromhex("06052b81040022")) == "P-384 (secp384r1)"
    assert oids.curve_of(b"\x05\x00") is None  # NULL parameters: not a named curve


def test_key_bits_by_algorithm():
    rsa = _rsa_der(b"\xf0" + b"\x11" * 255)
    assert oids.key_bits("1.2.840.113549.1.1.1", rsa, b"") == 2048
    assert oids.key_bits("1.2.840.10045.2.1", b"",
                         bytes.fromhex("06082a8648ce3d030107")) == 256
    assert oids.key_bits("1.2.840.10045.2.1", b"", b"\x05\x00") is None
    assert oids.key_bits("1.3.101.112", b"", b"") is None  # Ed25519: no helper yet


def test_oid_words():
    assert oids.signature_name("1.2.840.113549.1.1.11") == "sha256WithRSAEncryption"
    assert oids.signature_name("1.2.840.10045.4.3.2") == "ecdsaWithSHA256"
    assert oids.signature_name("9.9.9") is None
    assert oids.signature_name(None) is None
    assert oids.public_key_name("1.2.840.113549.1.1.1") == "RSA"
    assert oids.public_key_name("1.2.840.10045.2.1") == "EC"
    assert oids.purpose_name("1.3.6.1.5.5.7.3.1") == "server authentication"
    assert oids.purpose_name("1.3.6.1.5.5.7.3.3") == "code signing"
    assert oids.purpose_name("9.9.9") is None


# --- the validity words -----------------------------------------------------

def test_validity_words_matrix():
    def window(before_offset, after_offset):
        return tools.validity(NOW, NOW + before_offset, NOW + after_offset)

    expired = window(-DAY * 400, -DAY * 45 - 10)
    assert expired["state"] == "expired"
    assert expired["days_left"] == -45
    assert expired["note"] == "expired 45 day(s) ago"

    just_now = window(-DAY, -3600)
    assert just_now["state"] == "expired"
    assert just_now["note"] == "expired less than a day ago"

    expiring = window(-DAY, DAY * 12.5)
    assert expiring["state"] == "expiring"
    assert expiring["days_left"] == 12
    assert expiring["note"] == "expires in 12 day(s)"

    today = window(-DAY, 3600)
    assert today["state"] == "expiring"
    assert today["note"] == "expires today"

    valid = window(-DAY, DAY * 300.5)
    assert valid["state"] == "valid"
    assert valid["note"] == "valid for 300 more day(s)"

    future = window(DAY * 5.5, DAY * 400)
    assert future["state"] == "not_yet_valid"
    assert "not valid until" in future["note"]

    unknown = tools.validity(NOW, None, None)
    assert unknown["state"] == "unknown"


def test_iso_local_roundtrips_through_the_offset():
    text = tools._iso_local(NOW)
    assert re.search(r"[+-]\d{2}:\d{2}$", text), text  # local offset, not bare UTC
    assert datetime.fromisoformat(text).timestamp() == NOW
    assert tools._iso_local(None) is None


# --- the fakes ---------------------------------------------------------------

def facts(subject="Contoso Root CA", issuer=None, self_signed=True,
          not_before=NOW - DAY * 400, not_after=NOW + DAY * 900,
          thumbprint="AA" * 20, context="user", store="Root",
          signature_oid="1.2.840.113549.1.1.11", algorithm_oid="1.2.840.113549.1.1.1",
          key_bytes=None, parameters=b"", eku_oids=None, friendly=None,
          serial="00112233", version=2):
    return {
        "context": context, "store": store,
        "subject": subject, "issuer": issuer or subject,
        "self_signed": self_signed,
        "serial_hex": serial, "thumbprint": thumbprint,
        "friendly_name": friendly,
        "not_before": not_before, "not_after": not_after,
        "signature_oid": signature_oid,
        "public_key": {
            "algorithm_oid": algorithm_oid, "raw_size": len(key_bytes or b""),
            "key_bytes": key_bytes if key_bytes is not None
            else _rsa_der(b"\xf0" + b"\x11" * 255),
            "parameters": parameters,
        },
        "eku_oids": eku_oids, "version": version,
    }


ROWS = [
    facts(subject="Expired Personal Cert", thumbprint="BB" * 20, store="MY",
          self_signed=False, issuer="Ancient Issuer CA",
          not_after=NOW - DAY * 45, eku_oids=["1.3.6.1.5.5.7.3.1"],
          friendly="my-old-cert"),
    facts(subject="Contoso Root CA", thumbprint="AA" * 20, store="Root"),
    facts(subject="Soon Root CA", thumbprint="CC" * 20, store="Root",
          not_after=NOW + DAY * 12, context="machine"),
    facts(subject="Middle CA 1", thumbprint="DD" * 20, store="CA",
          self_signed=False, issuer="Enterprise Issuer CA",
          eku_oids=["2.5.29.37.0"], context="machine"),
]


@pytest.fixture
def fake_stores(monkeypatch):
    seen = {}

    def iter_certs(contexts=("user", "machine"), stores=certstore.DEFAULT_STORES):
        seen["contexts"], seen["stores"] = list(contexts), list(stores)
        return [dict(row) for row in ROWS]

    monkeypatch.setattr(certstore, "available", lambda: True)
    monkeypatch.setattr(certstore, "iter_certs", iter_certs)
    monkeypatch.setattr(tools.time, "time", lambda: NOW)
    return seen


def _payload(text):
    data = json.loads(text)
    assert data["ok"] is True, data
    return data


# --- the table tool ----------------------------------------------------------

def test_table_sorts_the_troubled_first(fake_stores):
    data = _payload(tools.win_cert_table({}))
    rows = data["certificates"]
    assert [row["state"] for row in rows][0] == "expired"
    assert rows[0]["thumbprint"] == "BB" * 20
    assert rows[1]["state"] == "expiring"
    assert {row["state"] for row in rows[2:]} == {"valid"}
    assert rows[0]["days_left"] == -45
    assert "self-signed" in " ".join(data["notes"])


def test_table_filters(fake_stores):
    expired = _payload(tools.win_cert_table({"expired_only": True}))
    assert [row["thumbprint"] for row in expired["certificates"]] == ["BB" * 20, "CC" * 20]

    by_name = _payload(tools.win_cert_table({"query": "contoso root"}))
    assert {row["thumbprint"] for row in by_name["certificates"]} == {"AA" * 20}

    none = _payload(tools.win_cert_table({"query": "no such ca"}))
    assert none["certificates"] == []
    assert any("nothing matched" in note for note in none["notes"])


def test_table_scopes_reach_the_walker(fake_stores):
    _payload(tools.win_cert_table({"context": "user", "store": "my"}))
    assert fake_stores["contexts"] == ["user"]
    assert fake_stores["stores"] == ["MY"]


def test_table_limit_and_note(fake_stores):
    data = _payload(tools.win_cert_table({"limit": 2}))
    assert len(data["certificates"]) == 2
    assert any("stopped at limit" in note for note in data["notes"])


def test_table_limit_is_clamped():
    assert tools._limit({"limit": 99999}) == 400
    assert tools._limit({"limit": 0}) == 1
    assert tools._limit({"limit": "junk"}) == 100


def test_table_refuses_non_windows(monkeypatch):
    monkeypatch.setattr(certstore, "available", lambda: False)
    data = json.loads(tools.win_cert_table({}))
    assert data["ok"] is False and data["code"] == "windows_only"


# --- the detail tool ---------------------------------------------------------

def test_detail_by_thumbprint_normalizes_punctuation(fake_stores):
    data = _payload(tools.win_cert_detail({"thumbprint": "bb bb bb bb bb bb bb bb bb bb bb bb bb bb bb bb bb bb bb bb"}))
    cert = data["certificate"]
    assert cert["subject"] == "Expired Personal Cert"
    assert cert["thumbprint"] == "BB" * 20
    assert cert["signature_algorithm"] == {
        "oid": "1.2.840.113549.1.1.11", "name": "sha256WithRSAEncryption"}
    assert cert["public_key"]["algorithm"]["name"] == "RSA"
    assert cert["public_key"]["bits"] == 2048
    assert cert["public_key"]["curve"] is None
    assert cert["purposes"] == [{"oid": "1.3.6.1.5.5.7.3.1", "name": "server authentication"}]
    assert cert["purposes_note"] is None
    assert cert["friendly_name"] == "my-old-cert"
    assert cert["version"] == "v2"
    assert cert["serial"] == "00112233"
    assert cert["validity"]["note"] == "expired 45 day(s) ago"


def test_detail_reports_missing_eku_as_any_purpose(fake_stores):
    data = _payload(tools.win_cert_detail({"query": "contoso root"}))
    cert = data["certificate"]
    assert cert["purposes"] is None
    assert "does not restrict" in cert["purposes_note"]


def test_detail_lists_candidates_when_ambiguous(fake_stores):
    data = _payload(tools.win_cert_detail({"query": "root ca"}))
    assert "certificate" not in data
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["thumbprint"]
    assert any("pick one by thumbprint" in note for note in data["notes"])


def test_detail_finds_multiple_copies_of_one_thumbprint(fake_stores):
    fake_rows = list(ROWS) + [
        facts(subject="Twin Cert", thumbprint="EE" * 20, context="user", store="MY"),
        facts(subject="Twin Cert", thumbprint="EE" * 20, context="machine", store="MY"),
    ]
    import hermes_windows_certificates.certstore as cs

    original = cs.iter_certs

    def with_twins(contexts=("user", "machine"), stores=cs.DEFAULT_STORES):
        return [dict(row) for row in fake_rows]

    cs.iter_certs = with_twins
    try:
        data = _payload(tools.win_cert_detail({"thumbprint": "ee" * 20}))
        assert data["certificate"]["subject"] == "Twin Cert"
        assert data["others"][0]["context"] == "machine"
        assert any("copies" in note for note in data["notes"])
    finally:
        cs.iter_certs = original


def test_detail_usage_and_no_match(fake_stores):
    usage = json.loads(tools.win_cert_detail({}))
    assert usage["ok"] is False and usage["code"] == "usage"

    missing = json.loads(tools.win_cert_detail({"thumbprint": "FF" * 20}))
    assert missing["ok"] is False and missing["code"] == "no_match"


# --- the register entry -------------------------------------------------------

def test_register_wires_both_tools():
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "certplugin_root", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["certplugin_root"] = module
    try:
        spec.loader.exec_module(module)

        registered = {}

        class Ctx:
            @staticmethod
            def register_tool(**kw):
                registered[kw["name"]] = kw

        module.register(Ctx)
    finally:
        sys.modules.pop("certplugin_root", None)
    assert set(registered) == {"win_cert_table", "win_cert_detail"}
    assert registered["win_cert_table"]["schema"]["name"] == "win_cert_table"
    # the freshly loaded module's handler is a twin of the imported one; the
    # wiring, not the object identity, is what this test pins down
    assert registered["win_cert_detail"]["handler"].__name__ == "win_cert_detail"
    assert registered["win_cert_detail"]["schema"]["name"] == "win_cert_detail"
