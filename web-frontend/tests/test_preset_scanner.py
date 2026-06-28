"""
Tests for preset_scanner.py — TDD RED phase.

Run with:
    cd D:\\codebaby\\Opencode--AIRP-SillyTavern\\web-frontend
    pytest tests/test_preset_scanner.py -v
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_preset(
    path: Path,
    name: str = "Test Preset",
    prompts: list[dict] | None = None,
    params: dict | None = None,
) -> None:
    data = {
        "name": name,
        "temperature": params.get("temperature", 1) if params else 1,
        "top_p": params.get("top_p", 1) if params else 1,
        "prompts": prompts
        or [
            {
                "name": "Main Prompt",
                "role": "system",
                "content": "You are {{char}}.",
                "identifier": "main",
                "injection_position": 0,
                "injection_depth": 4,
                "forbid_overrides": False,
                "injection_order": 100,
            },
            {
                "name": "NSFW Prompt",
                "role": "system",
                "content": "Be creative.",
                "identifier": "nsfw",
                "injection_position": 0,
                "injection_depth": 4,
                "forbid_overrides": False,
                "injection_order": 100,
            },
        ],
    }
    write_json(path, data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_presets_dir(tmp_path: Path) -> Path:
    """Create a temporary presets/ directory with sample files."""
    presets = tmp_path / "presets"
    presets.mkdir()
    return presets


@pytest.fixture()
def scanner(tmp_presets_dir: Path):
    """Import scanner lazily so module-not-found fails the test, not import."""
    from preset_scanner import PresetScanner

    return PresetScanner(presets_dir=tmp_presets_dir)


# ---------------------------------------------------------------------------
# Tests: PresetScanner.scan_all
# ---------------------------------------------------------------------------


class TestScanAll:
    def test_empty_directory(self, scanner: PresetScanner):
        from preset_scanner import PresetMeta

        result = scanner.scan_all()
        assert result == []

    def test_single_valid_preset(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(tmp_presets_dir / "preset1.json")

        result = scanner.scan_all()
        assert len(result) == 1
        assert result[0].name == "Test Preset"
        assert len(result[0].entries) == 2

    def test_multiple_presets(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(tmp_presets_dir / "a.json", name="Alpha")
        write_preset(tmp_presets_dir / "b.json", name="Beta")

        result = scanner.scan_all()
        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"Alpha", "Beta"}

    def test_skips_auxiliary_regex_files(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(tmp_presets_dir / "main.json", name="Main")
        # auxiliary files that should be skipped
        write_preset(tmp_presets_dir / "regex-abc.json", name="Regex ABC")
        write_preset(tmp_presets_dir / "quickreply-qr.json", name="QR")
        write_preset(tmp_presets_dir / "酒馆助手脚本-快速回复.json", name="QuickReply")

        result = scanner.scan_all()
        assert len(result) == 1
        assert result[0].name == "Main"

    def test_skips_auxiliary_case_insensitive(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(tmp_presets_dir / "REGEX-test.json", name="Should Skip")
        write_preset(tmp_presets_dir / "QR-test.json", name="Should Skip")

        result = scanner.scan_all()
        assert len(result) == 0

    def test_ignores_corrupted_json(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(tmp_presets_dir / "good.json", name="Good")
        (tmp_presets_dir / "bad.json").write_text("{ broken json!!!", encoding="utf-8")

        result = scanner.scan_all()
        assert len(result) == 1
        assert result[0].name == "Good"

    def test_ignores_non_json_files(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(tmp_presets_dir / "main.json", name="Main")
        (tmp_presets_dir / "readme.txt").write_text("hello", encoding="utf-8")
        (tmp_presets_dir / "script.js").write_text("console.log(1)", encoding="utf-8")

        result = scanner.scan_all()
        assert len(result) == 1

    def test_recursive_scan_subdirectories(self, scanner: PresetScanner, tmp_presets_dir: Path):
        sub = tmp_presets_dir / "sub1" / "sub2"
        sub.mkdir(parents=True)
        write_preset(sub / "deep.json", name="Deep")

        result = scanner.scan_all()
        assert len(result) == 1
        assert result[0].name == "Deep"


# ---------------------------------------------------------------------------
# Tests: PresetMeta / PresetEntry fields
# ---------------------------------------------------------------------------


class TestPresetMetaFields:
    def test_entry_fields_mapping(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(
            tmp_presets_dir / "p.json",
            name="MyPreset",
            prompts=[
                {
                    "name": "Main",
                    "role": "system",
                    "content": "Hello",
                    "identifier": "main",
                    "injection_position": 0,
                    "injection_depth": 4,
                    "forbid_overrides": True,
                    "injection_order": 100,
                },
                {
                    "name": "User Prompt",
                    "role": "user",
                    "content": "World",
                    "identifier": "dialogueExamples",
                    "injection_position": 1,
                    "injection_depth": 2,
                    "forbid_overrides": False,
                    "injection_order": 200,
                },
            ],
        )

        result = scanner.scan_all()
        assert len(result) == 1
        meta = result[0]
        assert meta.id == "p"
        assert meta.name == "MyPreset"
        assert len(meta.entries) == 2

        e0 = meta.entries[0]
        assert e0.id == "p_0"
        assert e0.name == "Main"
        assert e0.role == "system"
        assert e0.content == "Hello"
        assert e0.marker is False
        assert e0.enabled is True
        assert e0.injection_position == 0
        assert e0.injection_depth == 4
        assert e0.forbid_overrides is True
        assert e0.injection_order == 100
        assert e0.source_file.endswith("p.json")
        assert e0.preset_name == "MyPreset"

        e1 = meta.entries[1]
        assert e1.id == "p_1"
        assert e1.role == "user"
        assert e1.injection_position == 1

    def test_params_extraction(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_preset(
            tmp_presets_dir / "p.json",
            name="P",
            params={"temperature": 0.5, "top_p": 0.9},
        )
        # Note: write_preset helper embeds params in data, but we override after
        # for this test we just write directly
        write_json(
            tmp_presets_dir / "p.json",
            {
                "name": "P",
                "temperature": 0.5,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "max_tokens": 2048,
                "prompts": [],
            },
        )

        result = scanner.scan_all()
        assert len(result) == 1
        assert result[0].params["temperature"] == 0.5
        assert result[0].params["top_p"] == 0.9
        assert result[0].params["frequency_penalty"] == 0.1
        assert result[0].params["max_tokens"] == 2048

    def test_defaults_when_fields_missing(self, scanner: PresetScanner, tmp_presets_dir: Path):
        write_json(
            tmp_presets_dir / "p.json",
            {
                "name": "Minimal",
                "prompts": [
                    {"content": "Only content", "role": "system"},
                ],
            },
        )

        result = scanner.scan_all()
        assert len(result) == 1
        entry = result[0].entries[0]
        assert entry.name == "Only content" or entry.name == "Entry 0"
        assert entry.role == "system"
        assert entry.injection_position == 0
        assert entry.injection_depth == 4
        assert entry.enabled is True
