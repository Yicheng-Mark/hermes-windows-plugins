"""The ``wsl.exe`` wrappers, driven by recorded CLI output instead of a live distro."""

import subprocess
import sys

import pytest

from hermes_wsl_terminal import wsl


def completed(argv, returncode=0, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def utf16(text):
    return text.encode("utf-16-le")


class TestListDistros:
    def test_reads_utf16_names(self, monkeypatch):
        monkeypatch.setattr(wsl, "run_capture",
                            lambda argv, timeout=0: completed(argv, 0, utf16("Ubuntu-24.04\r\ndocker-desktop\r\n")))
        assert wsl.list_distros("wsl.exe") == ["Ubuntu-24.04", "docker-desktop"]

    def test_reports_the_cli_error(self, monkeypatch):
        monkeypatch.setattr(wsl, "run_capture",
                            lambda argv, timeout=0: completed(argv, 1, b"", utf16("WSL is not installed\r\n")))
        with pytest.raises(wsl.WslError) as exc:
            wsl.list_distros("wsl.exe")
        assert "WSL is not installed" in str(exc.value)

    def test_no_distros_is_an_empty_list(self, monkeypatch):
        monkeypatch.setattr(wsl, "run_capture", lambda argv, timeout=0: completed(argv, 0, utf16("")))
        assert wsl.list_distros("wsl.exe") == []


class TestDefaultDistro:
    def test_prefers_the_marked_row(self, monkeypatch):
        table = utf16("  NAME    STATE    VERSION\r\n* Debian  Stopped  2\r\n  Ubuntu  Stopped  2\r\n")
        calls = []

        def fake(argv, timeout=0):
            calls.append(argv)
            return completed(argv, 0, table if "-v" in argv else utf16("Ubuntu\r\nDebian\r\n"))

        monkeypatch.setattr(wsl, "run_capture", fake)
        assert wsl.default_distro("wsl.exe") == "Debian"
        assert calls == [["wsl.exe", "-l", "-v"]]

    def test_falls_back_to_the_first_registered(self, monkeypatch):
        def fake(argv, timeout=0):
            if "-v" in argv:
                return completed(argv, 0, utf16("  NAME    STATE    VERSION\r\n  Alpine  Stopped  2\r\n"))
            return completed(argv, 0, utf16("Alpine\r\ndocker-desktop\r\n"))

        monkeypatch.setattr(wsl, "run_capture", fake)
        assert wsl.default_distro("wsl.exe") == "Alpine"

    def test_an_old_wsl_without_dash_v_still_answers(self, monkeypatch):
        def fake(argv, timeout=0):
            if "-v" in argv:
                return completed(argv, 1, b"", utf16("Invalid command line option: -v\r\n"))
            return completed(argv, 0, utf16("Ubuntu-20.04\r\n"))

        monkeypatch.setattr(wsl, "run_capture", fake)
        assert wsl.default_distro("wsl.exe") == "Ubuntu-20.04"

    def test_nothing_installed(self, monkeypatch):
        def fake(argv, timeout=0):
            return completed(argv, 0, utf16(""))

        monkeypatch.setattr(wsl, "run_capture", fake)
        assert wsl.default_distro("wsl.exe") is None


class TestVersion:
    def test_reports_the_line_verbatim_including_locale(self, monkeypatch):
        line = "WSL \u7248\u672c: 3.0.3.0"
        monkeypatch.setattr(wsl, "run_capture",
                            lambda argv, timeout=0: completed(argv, 0, utf16(f"{line}\r\nKernel: 6.18\r\n")))
        assert wsl.version("wsl.exe") == line

    def test_old_wsl_reports_nothing(self, monkeypatch):
        monkeypatch.setattr(wsl, "run_capture", lambda argv, timeout=0: completed(argv, 1))
        assert wsl.version("wsl.exe") == ""


class TestPathProbes:
    def test_to_unix_path_quotes_the_windows_path(self, monkeypatch):
        seen = {}

        def fake(argv, timeout=0):
            seen["argv"] = argv
            return completed(argv, 0, b"/mnt/c/Users/me/")

        monkeypatch.setattr(wsl, "run_capture", fake)
        assert wsl.to_unix_path("wsl.exe", "Ubuntu", r"C:\Users\me") == "/mnt/c/Users/me/"
        # wsl.exe runs what follows -- through a shell, so the path must arrive quoted or its
        # backslashes are eaten as escapes.
        assert seen["argv"][:5] == ["wsl.exe", "-d", "Ubuntu", "--", "/bin/sh"]
        assert seen["argv"][5] == "-c"
        assert seen["argv"][6] == "wslpath -u 'C:\\Users\\me'"

    def test_to_unix_path_failure_is_none(self, monkeypatch):
        monkeypatch.setattr(wsl, "run_capture",
                            lambda argv, timeout=0: completed(argv, 1, b"", b"wslpath: invalid"))
        assert wsl.to_unix_path("wsl.exe", "Ubuntu", r"C:\Users\me") is None

    def test_mount_root_uses_wslpath(self, monkeypatch):
        seen = {}

        def fake(argv, timeout=0):
            seen["argv"] = argv
            return completed(argv, 0, b"/drives/c/")

        monkeypatch.setattr(wsl, "run_capture", fake)
        assert wsl.mount_root("wsl.exe", "Ubuntu") == "/drives"
        assert seen["argv"][:5] == ["wsl.exe", "-d", "Ubuntu", "--", "/bin/sh"]
        assert seen["argv"][-1] == "wslpath -u 'C:\\'"

    def test_mount_root_falls_back_when_wslpath_is_missing(self, monkeypatch):
        monkeypatch.setattr(wsl, "run_capture",
                            lambda argv, timeout=0: completed(argv, 127, b"", b"wslpath: not found"))
        assert wsl.mount_root("wsl.exe", "Ubuntu") == "/mnt"


class TestResolveWsl:
    @pytest.mark.skipif(sys.platform != "win32", reason="wsl.exe only exists on Windows")
    def test_finds_the_binary_on_this_host(self):
        assert wsl.resolve_wsl().lower().endswith("wsl.exe") or wsl.resolve_wsl().lower().endswith("wsl")

    def test_explicit_failure_message_when_absent(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(wsl.WslError) as exc:
            wsl.resolve_wsl()
        assert "Windows" in str(exc.value)


class TestRunCapture:
    def test_passes_bytes_through_untouched(self, monkeypatch):
        recorded = {}

        class FakeRun:
            @staticmethod
            def run(argv, **kwargs):
                recorded.update(kwargs)
                recorded["argv"] = argv
                return completed(argv, 0, b"\xff\xfehello")

        monkeypatch.setattr(wsl.subprocess, "run", FakeRun.run)
        result = wsl.run_capture(["wsl.exe", "-l", "-q"])
        assert result.stdout == b"\xff\xfehello"
        assert recorded["stdin"] == subprocess.DEVNULL
        assert recorded["argv"] == ["wsl.exe", "-l", "-q"]

    def test_missing_binary_becomes_a_wsl_error(self, monkeypatch):
        def boom(argv, **kwargs):
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(wsl.subprocess, "run", boom)
        with pytest.raises(wsl.WslError):
            wsl.run_capture(["wsl.exe"])
