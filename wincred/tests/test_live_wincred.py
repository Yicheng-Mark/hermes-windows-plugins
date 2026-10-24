"""Live end-to-end against the real Windows Credential Manager.

Opt-in: writing a credential touches the current user's real vault, so this runs only
with ``HERMES_WINCRED_LIVE=1`` (and only on Windows). Every credential it creates is
deleted in the fixture teardown.
"""

import codecs
import os
import uuid
from pathlib import Path

import pytest

pytest.importorskip(
    "agent.secret_sources.base",
    reason="Hermes core is not installed; run with PYTHONPATH pointing at a Hermes checkout",
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.name != "nt", reason="Windows Credential Manager is Windows-only"),
    pytest.mark.skipif(
        os.environ.get("HERMES_WINCRED_LIVE") != "1",
        reason="set HERMES_WINCRED_LIVE=1 to touch the real credential vault",
    ),
]

from hermes_wincred import credman  # noqa: E402
from hermes_wincred.source import WinCredSource  # noqa: E402

from credman_support import delete_generic, write_generic  # noqa: E402


@pytest.fixture
def target():
    name = f"hermes-wincred-test/{uuid.uuid4().hex}"
    yield name
    delete_generic(name)


def _fetch(mapping):
    return WinCredSource().fetch({"map": mapping}, Path("."))


def test_reads_a_utf8_credential(target):
    write_generic(target, b"sk-live-utf8-123")
    result = _fetch({"HERMES_TEST_KEY": target})
    assert result.ok
    assert result.secrets == {"HERMES_TEST_KEY": "sk-live-utf8-123"}
    assert result.warnings == []


def test_reads_a_utf16_credential(target):
    write_generic(target, codecs.BOM_UTF16_LE + "sk-live-utf16".encode("utf-16-le"))
    result = _fetch({"HERMES_TEST_KEY": target})
    assert result.ok
    assert result.secrets == {"HERMES_TEST_KEY": "sk-live-utf16"}


def test_missing_target_warns_without_failing_other_entries(target):
    write_generic(target, b"sk-present")
    result = _fetch({
        "PRESENT_KEY": target,
        "ABSENT_KEY": target + "/absent",
    })
    assert result.ok
    assert result.secrets == {"PRESENT_KEY": "sk-present"}
    assert any("no generic credential" in w for w in result.warnings)


def test_missing_target_raises_not_found():
    assert credman.available() is True
    with pytest.raises(credman.CredManError) as excinfo:
        credman.read_generic(f"hermes-wincred-test/{uuid.uuid4().hex}")
    assert excinfo.value.code == credman.ERROR_NOT_FOUND
