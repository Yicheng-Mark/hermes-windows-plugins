"""Package sanity for the hermes-windows-ops plugin.

Stdlib + pytest only, no network. These check the things a reviewer has to
check by hand otherwise: the manifest is well formed, every skill declares
itself correctly, and the skill's section and reference structure matches what
the repository's skill guidelines ask for.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILES = sorted(ROOT.glob("skills/*/SKILL.md"))
REQUIRED_SECTIONS = ("## Quick Reference", "## Procedure", "## Pitfalls", "## Verification")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the simple ``key: value`` frontmatter these skills use."""
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must open with a YAML frontmatter block")

    end = text.index("\n---\n", 3)
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        if not _:
            raise AssertionError(f"frontmatter line is not a key/value pair: {line!r}")
        fields[key.strip()] = value.strip()

    return fields


def test_manifest_is_valid_and_complete():
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))

    for field in ("name", "version", "description", "repository", "license"):
        assert manifest.get(field), f"plugin.json is missing {field}"

    assert "author" in manifest and manifest["author"].get("name")
    assert manifest["$schema"].endswith("plugin.schema.json")


def test_manifest_name_is_a_kebab_case_identifier():
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))

    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", manifest["name"]), manifest["name"]


def test_at_least_one_skill_ships():
    assert SKILL_FILES, "the plugin declares no skills"


@pytest.mark.parametrize("skill_md", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_frontmatter_matches_its_directory(skill_md: Path):
    fields = parse_frontmatter(skill_md.read_text(encoding="utf-8"))

    assert fields.get("name") == skill_md.parent.name
    description = fields.get("description", "")

    assert len(description) >= 40, "description is too short to trigger reliably"
    assert len(description) <= 1024, "description exceeds the 1024 character cap"
    assert "<" not in description and ">" not in description, "angle brackets break frontmatter"
    assert "\n" not in description


@pytest.mark.parametrize("skill_md", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_the_expected_sections(skill_md: Path):
    body = skill_md.read_text(encoding="utf-8")

    for section in REQUIRED_SECTIONS:
        assert section in body, f"{skill_md.parent.name} is missing {section}"


@pytest.mark.parametrize("skill_md", SKILL_FILES, ids=lambda p: p.parent.name)
def test_relative_references_resolve(skill_md: Path):
    body = skill_md.read_text(encoding="utf-8")
    skill_dir = skill_md.parent

    for target in re.findall(r"`(references/[^`]+\.md)`", body):
        assert (skill_dir / target).is_file(), f"{skill_md.parent.name} points at a missing {target}"


def test_package_ships_no_executable_payloads():
    banned = {".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".zip", ".tar", ".gz", ".wasm"}

    offenders = [p.relative_to(ROOT) for p in ROOT.rglob("*") if p.suffix.lower() in banned]

    assert not offenders, f"unreviewable payloads in the package: {offenders}"
