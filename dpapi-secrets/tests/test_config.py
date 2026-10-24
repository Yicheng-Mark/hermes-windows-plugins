from pathlib import Path

from hermes_dpapi_secrets.config import DEFAULT_FILENAME, parse_map, store_path


def test_parses_env_to_store_names():
    mapping, warnings = parse_map(
        {"map": {"OPENAI_API_KEY": "openai", "ZAI_API_KEY": "dpapi://zai"}}
    )
    assert mapping == {"OPENAI_API_KEY": "openai", "ZAI_API_KEY": "zai"}
    assert warnings == []


def test_bad_env_name_is_skipped_with_a_warning():
    mapping, warnings = parse_map({"map": {"not-a-name": "x", "GOOD": "y"}})
    assert mapping == {"GOOD": "y"}
    assert any("not-a-name" in warning for warning in warnings)


def test_non_string_and_empty_refs_are_skipped():
    mapping, warnings = parse_map({"map": {"A": None, "B": "   ", "C": "  ok  "}})
    assert mapping == {"C": "ok"}
    assert len(warnings) == 2


def test_missing_or_wrong_map_shape_never_raises():
    for cfg in ({}, {"map": "nope"}, {"map": []}, None, "not-a-dict", 7):
        mapping, warnings = parse_map(cfg)
        assert mapping == {}
        assert warnings, f"expected a warning for cfg={cfg!r}"


def test_store_path_defaults_to_the_home_directory():
    home = Path("/home/user/.hermes")
    assert store_path({}, home) == home / DEFAULT_FILENAME
    assert store_path({"file": "  "}, home) == home / DEFAULT_FILENAME
    assert store_path({"file": 3}, home) == home / DEFAULT_FILENAME


def test_relative_path_is_relative_to_the_home():
    home = Path("/home/user/.hermes")
    assert store_path({"file": "nested/secrets.dpapi"}, home) == \
        home / "nested" / "secrets.dpapi"


def test_absolute_path_is_used_as_is():
    home = Path("/home/user/.hermes")
    assert store_path({"file": "/etc/hermes/secrets.dpapi"}, home) == \
        Path("/etc/hermes/secrets.dpapi")
