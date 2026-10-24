"""End-to-end checks against a real distro on this machine.

Enabled with ``HERMES_WSL_LIVE=1``; set ``HERMES_SOURCE`` to a hermes-agent checkout when
Hermes itself is not importable from the current interpreter. Every test below runs a real
command through ``wsl.exe``.
"""

import os
import shlex
import sys
import tempfile
from pathlib import Path

import pytest

from hermes_wsl_terminal import wsl
from hermes_wsl_terminal.config import ENV_DISTRO

LIVE = os.environ.get("HERMES_WSL_LIVE") == "1"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE, reason="set HERMES_WSL_LIVE=1 to run against a real distro"),
]


@pytest.fixture(scope="module")
def env():
    source = os.environ.get("HERMES_SOURCE")
    if source:
        sys.path.insert(0, str(Path(source).expanduser().resolve()))
    try:
        from hermes_wsl_terminal.environment import WslEnvironment
    except ImportError as exc:
        pytest.skip(f"Hermes is not importable here ({exc}); set HERMES_SOURCE")
    exe = wsl.resolve_wsl()
    distros = wsl.list_distros(exe)
    if not distros:
        pytest.skip("no WSL distro installed")
    distro = os.environ.get(ENV_DISTRO) or wsl.default_distro(exe) or distros[0]
    environment = WslEnvironment(exe=exe, distro=distro, cwd=os.getcwd(), timeout=60)
    yield environment
    environment.cleanup()


def test_commands_run_in_linux(env):
    result = env.execute("uname -s; id -un")
    assert result["returncode"] == 0
    lines = result["output"].strip().splitlines()
    assert lines[0] == "Linux"
    assert lines[1].strip()


def test_windows_cwd_is_the_project_directory(env):
    expected = env.translate(os.getcwd())
    result = env.execute("pwd")
    assert result["output"].strip().splitlines()[-1] == expected


def test_translation_matches_wslpath(env):
    """The in-process rule has to agree with the tool the distro ships."""
    for host_path in (os.getcwd(), tempfile.gettempdir(), r"C:\Windows"):
        ours = env.translate(host_path)
        theirs = wsl.to_unix_path(env.executable, env.distro, host_path)
        assert theirs is not None, host_path
        assert ours.rstrip("/") == theirs.rstrip("/"), host_path


def test_the_same_file_is_visible_on_both_sides(env):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        handle.write("visible from the distro\n")
        host_path = handle.name
    try:
        unix_path = env.translate(host_path)
        result = env.execute(f"cat {shlex.quote(unix_path)}")
        assert result["returncode"] == 0
        assert "visible from the distro" in result["output"]
    finally:
        os.unlink(host_path)


def test_stdin_is_forwarded(env):
    result = env.execute("cat", stdin_data="line one\nline two\n")
    assert result["returncode"] == 0
    assert "line one" in result["output"] and "line two" in result["output"]


def test_exit_code_and_contract_field(env):
    result = env.execute("exit 7")
    assert result["returncode"] == 7
    assert result["exit_code"] == 7


def test_unicode_output(env):
    result = env.execute("printf '%s\\n' '\u4e2d\u6587 OK \u2713'")
    assert result["returncode"] == 0
    assert "\u4e2d\u6587 OK \u2713" in result["output"]


def test_cwd_persists_between_calls(env):
    env.execute("cd /tmp")
    result = env.execute("pwd")
    assert result["output"].strip().splitlines()[-1] == "/tmp"
    env.execute(f"cd {shlex.quote(env.translate(os.getcwd()))}")


def test_a_per_call_host_cwd_is_translated(env):
    with tempfile.TemporaryDirectory() as folder:
        result = env.execute("pwd", cwd=folder)
        assert result["output"].strip().splitlines()[-1] == env.translate(folder)
