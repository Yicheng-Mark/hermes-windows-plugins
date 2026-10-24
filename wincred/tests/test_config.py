from hermes_wincred.config import parse_map


def test_bare_target_and_scheme_are_equivalent():
    mapping, warnings = parse_map({
        "map": {
            "ZAI_API_KEY": "hermes/zai",
            "OPENAI_API_KEY": "wincred://hermes/openai",
        }
    })
    assert mapping == {"ZAI_API_KEY": "hermes/zai", "OPENAI_API_KEY": "hermes/openai"}
    assert warnings == []


def test_scheme_is_case_insensitive_and_target_is_trimmed():
    mapping, _ = parse_map({"map": {"TOKEN": "  WinCred://  vault/item  "}})
    assert mapping == {"TOKEN": "vault/item"}


def test_malformed_entries_are_skipped_with_warnings():
    mapping, warnings = parse_map({
        "map": {
            "GOOD": "ok",
            "bad-name": "x",
            "LOWER ok": "x",
            "": "x",
            "MISSING": "",
            "NOT_STR": 7,
            "SCHEME_ONLY": "wincred://",
        }
    })
    assert mapping == {"GOOD": "ok"}
    assert len(warnings) == 6
    assert any("bad-name" in w for w in warnings)
    assert any("MISSING" in w for w in warnings)


def test_non_mapping_sections_never_raise():
    for cfg in (None, [], "x", 3):
        mapping, warnings = parse_map(cfg)
        assert mapping == {}
        assert warnings


def test_missing_or_wrong_map():
    assert parse_map({})[0] == {}
    assert parse_map({"enabled": True})[0] == {}
    mapping, warnings = parse_map({"map": ["A", "B"]})
    assert mapping == {}
    assert warnings


def test_empty_map():
    assert parse_map({"map": {}}) == ({}, [])
