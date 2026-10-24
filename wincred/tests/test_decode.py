import codecs

import pytest

from hermes_wincred.credman import CredentialDecodeError, decode_secret


def test_utf8_is_the_default():
    assert decode_secret(b"sk-test-123") == "sk-test-123"


def test_utf16_with_bom():
    raw = codecs.BOM_UTF16_LE + "ключ-123".encode("utf-16-le")
    assert decode_secret(raw) == "ключ-123"


def test_utf16le_without_bom_is_detected():
    raw = "sk-utf16".encode("utf-16-le")
    assert decode_secret(raw) == "sk-utf16"


def test_trailing_nul_is_stripped():
    assert decode_secret(b"abc\x00") == "abc"
    assert decode_secret("abc".encode("utf-16-le") + b"\x00\x00") == "abc"


def test_empty_blob_is_empty_text():
    assert decode_secret(b"") == ""


def test_binary_garbage_fails_closed():
    with pytest.raises(CredentialDecodeError):
        decode_secret(b"\xff\xfe\x00\x80\x81")
    with pytest.raises(CredentialDecodeError):
        decode_secret(b"\xff\x00\xfe")
