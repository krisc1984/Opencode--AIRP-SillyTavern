"""Tests for airp_context.py preset integration — TDD RED phase."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from airp_context import build_context, get_context_payload, write_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_preset(tmp_path: Path, name: str, prompts: list[dict]) -> Path:
    """Write a minimal preset JSON file and return its path."""
    preset = {
        "temperature": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "top_p": 1.0,
        "top_k": 0,
        "top_a": 0,
        "min_p": 0,
        "repetition_penalty": 1,
        "openai_max_context": 4096,
        "openai_max_tokens": 2048,
        "wrap_in_quotes": False,
        "names_behavior": 0,
        "send_if_empty": "",
        "impersonation_prompt": "",
        "new_chat_prompt": "",
        "new_group_chat_prompt": "",
        "new_example_chat_prompt": "",
        "continue_nudge_prompt": "",
        "bias_preset_selected": "Default (none)",
        "max_context_unlocked": True,
        "wi_format": "{0}",
        "scenario_format": "{{scenario}}",
        "personality_format": "{{personality}}",
        "group_nudge_prompt": "",
        "stream_openai": True,
        "prompts": prompts,
    }
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(preset, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests: build_context includes assembled presets
# ---------------------------------------------------------------------------


class TestBuildContextPresets:
    def test_no_presets_when_no_preset_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When presets dir doesn't exist, context should have empty preset blocks."""
        monkeypatch.setenv("AIRP_PRESETS_DIR", str(tmp_path / "nonexistent"))
        payload = build_context("card-1", "hello")
        assert payload["assembledPresets"] == {}

    def test_empty_presets_when_dir_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When presets dir exists but has no JSON files, context should have empty preset blocks."""
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir()
        monkeypatch.setenv("AIRP_PRESETS_DIR", str(presets_dir))
        payload = build_context("card-1", "hello")
        assert payload["assembledPresets"] == {}

    def test_single_enabled_entry_assembled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A single enabled entry should appear in assembledPresets."""
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir()
        _write_preset(
            presets_dir,
            "p1",
            [
                {
                    "identifier": "e1",
                    "name": "Test Entry",
                    "enabled": True,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 100,
                    "role": "system",
                    "content": "You are a test.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                }
            ],
        )
        monkeypatch.setenv("AIRP_PRESETS_DIR", str(presets_dir))
        payload = build_context("card-1", "hello")
        assert "p1" in payload["assembledPresets"]
        assert len(payload["assembledPresets"]["p1"]) == 1
        assert payload["assembledPresets"]["p1"][0]["id"] == "p1_0"
        assert payload["assembledPresets"]["p1"][0]["content"] == "You are a test."

    def test_disabled_entry_excluded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Disabled entries should not appear in assembledPresets."""
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir()
        _write_preset(
            presets_dir,
            "p1",
            [
                {
                    "identifier": "e1",
                    "name": "Enabled",
                    "enabled": True,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 100,
                    "role": "system",
                    "content": "Enabled content.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                },
                {
                    "identifier": "e2",
                    "name": "Disabled",
                    "enabled": False,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 100,
                    "role": "system",
                    "content": "Disabled content.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                },
            ],
        )
        monkeypatch.setenv("AIRP_PRESETS_DIR", str(presets_dir))
        payload = build_context("card-1", "hello")
        assert len(payload["assembledPresets"]["p1"]) == 1
        assert payload["assembledPresets"]["p1"][0]["id"] == "p1_0"

    def test_entries_sorted_by_injection_order(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Entries should be sorted by injection_order within each preset."""
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir()
        _write_preset(
            presets_dir,
            "p1",
            [
                {
                    "identifier": "e1",
                    "name": "First",
                    "enabled": True,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 200,
                    "role": "system",
                    "content": "Second.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                },
                {
                    "identifier": "e2",
                    "name": "Second",
                    "enabled": True,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 100,
                    "role": "system",
                    "content": "First.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                },
            ],
        )
        monkeypatch.setenv("AIRP_PRESETS_DIR", str(presets_dir))
        payload = build_context("card-1", "hello")
        entries = payload["assembledPresets"]["p1"]
        assert entries[0]["id"] == "p1_1"
        assert entries[1]["id"] == "p1_0"

    def test_multiple_presets_assembled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Multiple preset files should each appear in assembledPresets."""
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir()
        _write_preset(
            presets_dir,
            "p1",
            [
                {
                    "identifier": "e1",
                    "name": "P1 Entry",
                    "enabled": True,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 100,
                    "role": "system",
                    "content": "From P1.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                }
            ],
        )
        _write_preset(
            presets_dir,
            "p2",
            [
                {
                    "identifier": "e2",
                    "name": "P2 Entry",
                    "enabled": True,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 100,
                    "role": "system",
                    "content": "From P2.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                }
            ],
        )
        monkeypatch.setenv("AIRP_PRESETS_DIR", str(presets_dir))
        payload = build_context("card-1", "hello")
        assert "p1" in payload["assembledPresets"]
        assert "p2" in payload["assembledPresets"]
        assert payload["assembledPresets"]["p1"][0]["content"] == "From P1."
        assert payload["assembledPresets"]["p2"][0]["content"] == "From P2."

    def test_auxiliary_files_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Files like quickreply/regex should be ignored as auxiliary."""
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir()
        _write_preset(
            presets_dir,
            "p1",
            [
                {
                    "identifier": "e1",
                    "name": "Main",
                    "enabled": True,
                    "injection_position": 0,
                    "injection_depth": 4,
                    "injection_order": 100,
                    "role": "system",
                    "content": "Main preset.",
                    "system_prompt": False,
                    "marker": False,
                    "forbid_overrides": False,
                }
            ],
        )
        # Write auxiliary files that should be ignored
        (presets_dir / "qr-quickreply.json").write_text("{}", encoding="utf-8")
        (presets_dir / "regex-test.json").write_text("{}", encoding="utf-8")
        (presets_dir / "快速回复.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("AIRP_PRESETS_DIR", str(presets_dir))
        payload = build_context("card-1", "hello")
        assert "p1" in payload["assembledPresets"]
        assert "qr-quickreply" not in payload["assembledPresets"]
        assert "regex-test" not in payload["assembledPresets"]
        assert "快速回复" not in payload["assembledPresets"]
