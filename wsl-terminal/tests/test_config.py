"""Translation and parsing rules, proved without a Hermes install or a WSL distro."""

import pytest

from hermes_wsl_terminal.config import (
    DEFAULT_MOUNT_ROOT,
    decode_cli_output,
    mount_root_from_c_drive,
    parse_default_distro,
    parse_distro_list,
    resolve_distro,
    to_posix_path,
)


class TestToPosixPath:
    @pytest.mark.parametrize("host_path, expected", [
        (r"C:\Users\me\proj", "/mnt/c/Users/me/proj"),
        ("C:/Users/me/proj", "/mnt/c/Users/me/proj"),
        (r"d:\work\a b\c", "/mnt/d/work/a b/c"),
        (r"C:\Users\me\Desktop\claude chat", "/mnt/c/Users/me/Desktop/claude chat"),
    ])
    def test_drive_paths_land_under_the_mount_root(self, host_path, expected):
        assert to_posix_path(host_path) == expected

    def test_drive_root_without_a_suffix(self):
        assert to_posix_path("C:") == "/mnt/c"
        assert to_posix_path("C:\\") == "/mnt/c"
        assert to_posix_path("C:/") == "/mnt/c"

    @pytest.mark.parametrize("host_path", [
        r"\\wsl.localhost\Ubuntu-24.04\home\me\proj",
        r"\\wsl$\Ubuntu-24.04\home\me\proj",
        r"//wsl.localhost/Ubuntu-24.04/home/me/proj",
        r"//wsl$/Ubuntu-24.04/home/me/proj",
    ])
    def test_unc_shares_address_the_distro_filesystem(self, host_path):
        assert to_posix_path(host_path) == "/home/me/proj"

    def test_unc_share_naming_only_a_distro_is_the_root(self):
        assert to_posix_path(r"\\wsl$\Ubuntu-24.04") == "/"

    def test_other_unc_shares_are_left_alone(self):
        # A network share is not reachable from inside the distro; rewriting it would point
        # the command at a path that cannot exist.
        assert to_posix_path(r"\\server\share\dir") == "//server/share/dir"

    @pytest.mark.parametrize("path", ["/home/me/proj", "/", "/tmp", "~/proj", "~"])
    def test_linux_side_paths_pass_through(self, path):
        assert to_posix_path(path) == path

    @pytest.mark.parametrize("path, expected", [("", "~"), ("   ", "~"), ("~/", "~")])
    def test_empty_and_home_shapes_become_tilde(self, path, expected):
        assert to_posix_path(path) == expected

    def test_relative_paths_pass_through(self):
        assert to_posix_path("src/app.py") == "src/app.py"
        assert to_posix_path(r"src\app.py") == "src/app.py"

    def test_custom_mount_root(self):
        assert to_posix_path(r"C:\work", mount_root="/") == "/c/work"
        assert to_posix_path(r"C:\work", mount_root="/drives/") == "/drives/c/work"


class TestMountRootFromCDrive:
    @pytest.mark.parametrize("reported, expected", [
        ("/mnt/c/", "/mnt"),
        ("/mnt/c", "/mnt"),
        ("/c/", ""),
        ("/c", ""),
        ("/windows/c/", "/windows"),
    ])
    def test_derives_the_root(self, reported, expected):
        assert mount_root_from_c_drive(reported) == expected

    @pytest.mark.parametrize("reported", ["", "not a path", "/mnt/c/Users"])
    def test_unexpected_output_falls_back_to_the_default(self, reported):
        assert mount_root_from_c_drive(reported) == DEFAULT_MOUNT_ROOT


class TestDecodeCliOutput:
    def test_utf16le_without_bom(self):
        # `wsl.exe -l -q` on a redirected stdout, byte for byte.
        raw = "Ubuntu-24.04\r\n".encode("utf-16-le")
        assert decode_cli_output(raw) == "Ubuntu-24.04\r\n"

    def test_utf16le_with_bom(self):
        raw = b"\xff\xfe" + "Ubuntu".encode("utf-16-le")
        assert decode_cli_output(raw) == "Ubuntu"

    def test_plain_utf8(self):
        assert decode_cli_output("hello\n".encode("utf-8")) == "hello\n"

    def test_utf8_non_ascii_is_not_mistaken_for_utf16(self):
        assert decode_cli_output("中文 OK".encode("utf-8")) == "中文 OK"

    def test_empty(self):
        assert decode_cli_output(b"") == ""


class TestListingParsers:
    def test_distro_list(self):
        text = "Ubuntu-24.04\r\ndocker-desktop\r\n\r\n"
        assert parse_distro_list(text) == ["Ubuntu-24.04", "docker-desktop"]

    def test_default_distro(self):
        text = ("  NAME            STATE           VERSION\r\n"
                "* Ubuntu-24.04    Stopped         2\r\n"
                "  docker-desktop  Stopped         2\r\n")
        assert parse_default_distro(text) == "Ubuntu-24.04"

    def test_no_default_marker(self):
        text = "  NAME    STATE    VERSION\n  Alpine  Stopped  2\n"
        assert parse_default_distro(text) is None


class TestResolveDistro:
    def test_explicit_wins(self):
        assert resolve_distro("Debian", ["Ubuntu", "Debian"], "Ubuntu") == "Debian"

    def test_explicit_is_trimmed(self):
        assert resolve_distro("  Debian  ", ["Debian"], None) == "Debian"

    def test_default_wins_over_registration_order(self):
        assert resolve_distro("", ["Ubuntu", "Debian"], "Debian") == "Debian"

    def test_first_registered_when_nothing_marks_a_default(self):
        assert resolve_distro(None, ["Ubuntu", "Debian"], None) == "Ubuntu"

    def test_no_distros(self):
        assert resolve_distro(None, [], None) is None
