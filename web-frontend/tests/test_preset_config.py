"""
Tests for preset_config.py — TDD RED phase.

Run with:
    cd D:\\codebaby\\Opencode--AIRP-SillyTavern\\web-frontend
    pytest tests/test_preset_config.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from preset_scanner import PresetEntry, PresetMeta, PresetScanner
from preset_config import PresetConfig, PresetConfigManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_entry(entry_id: str, name: str = "Entry") -> PresetEntry:
    return PresetEntry(
        id=entry_id,
        name=name,
        role="system",
        content=f"content of {entry_id}",
        marker=False,
        enabled=True,
        injection_position=0,
        injection_depth=4,
        injection_order=100,
        forbid_overrides=False,
        source_file="presets/x.json",
        preset_name="TestPreset",
    )


def make_meta(entry_ids: list[str]) -> PresetMeta:
    return PresetMeta(
        id="test-preset",
        name="TestPreset",
        source=Path("presets/test-preset.json"),
        entries=[make_entry(eid) for eid in entry_ids],
        params={"temperature": 1},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "preset-config.json"


@pytest.fixture()
def manager(config_path: Path):
    from preset_config import PresetConfigManager

    return PresetConfigManager(config_path=config_path)


@pytest.fixture()
def scanner_with_presets(tmp_path: Path):
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    scanner = PresetScanner(presets_dir=presets_dir)

    # We monkey-patch scan_all by injecting pre-built metas
    # because the scanner reads from disk. For config tests we want
    # deterministic metadata without touching the real presets/ tree.
    return scanner


# ---------------------------------------------------------------------------
# Tests: load / save
# ---------------------------------------------------------------------------


class TestLoadSave:
    def test_default_when_file_missing(self, manager: PresetConfigManager):
        from preset_config import PresetConfig

        cfg = manager.load()
        assert isinstance(cfg, PresetConfig)
        assert cfg.active_preset_id == ""
        assert cfg.presets == {}

    def test_roundtrip_preserves_data(self, manager: PresetConfigManager, config_path: Path):
        from preset_config import PresetConfig

        original = PresetConfig(
            active_preset_id="p1",
            presets={
                "p1": {
                    "source": "presets/p1.json",
                    "enabled": True,
                    "entries": {
                        "e1": {"enabled": True, "order": 1},
                        "e2": {"enabled": False, "order": 2},
                    },
                }
            },
        )
        manager.save(original)
        assert config_path.exists()

        loaded = manager.load()
        assert loaded.active_preset_id == "p1"
        assert loaded.presets["p1"]["source"] == "presets/p1.json"
        assert loaded.presets["p1"]["entries"]["e1"]["enabled"] is True
        assert loaded.presets["p1"]["entries"]["e2"]["enabled"] is False

    def test_file_is_valid_json(self, manager: PresetConfigManager, config_path: Path):
        manager.save(manager.load())
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert "activePresetId" in raw
        assert "presets" in raw


# ---------------------------------------------------------------------------
# Tests: toggle_entry
# ---------------------------------------------------------------------------


class TestToggleEntry:
    def test_toggle_enabled_true(self, manager: PresetConfigManager):
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {"e1": {"enabled": False, "order": 1}},
                    }
                },
            )
        )

        manager.toggle_entry("p1", "e1", True)
        cfg = manager.load()
        assert cfg.presets["p1"]["entries"]["e1"]["enabled"] is True

    def test_toggle_enabled_false(self, manager: PresetConfigManager):
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {"e1": {"enabled": True, "order": 1}},
                    }
                },
            )
        )

        manager.toggle_entry("p1", "e1", False)
        cfg = manager.load()
        assert cfg.presets["p1"]["entries"]["e1"]["enabled"] is False

    def test_toggle_creates_missing_preset_block(self, manager: PresetConfigManager):
        manager.save(PresetConfig(active_preset_id="p-new", presets={}))
        manager.toggle_entry("p-new", "e1", True)
        cfg = manager.load()
        assert "p-new" in cfg.presets
        assert cfg.presets["p-new"]["entries"]["e1"]["enabled"] is True


# ---------------------------------------------------------------------------
# Tests: reorder_entries
# ---------------------------------------------------------------------------


class TestReorderEntries:
    def test_reorder_changes_order(self, manager: PresetConfigManager):
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {
                            "a": {"enabled": True, "order": 1},
                            "b": {"enabled": True, "order": 2},
                            "c": {"enabled": True, "order": 3},
                        },
                    }
                },
            )
        )

        manager.reorder_entries("p1", ["c", "a", "b"])
        cfg = manager.load()
        entries = cfg.presets["p1"]["entries"]
        assert list(entries.keys()) == ["c", "a", "b"]
        assert entries["c"]["order"] == 1
        assert entries["a"]["order"] == 2
        assert entries["b"]["order"] == 3

    def test_reorder_preserves_enabled_flags(self, manager: PresetConfigManager):
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {
                            "a": {"enabled": False, "order": 1},
                            "b": {"enabled": True, "order": 2},
                        },
                    }
                },
            )
        )

        manager.reorder_entries("p1", ["b", "a"])
        cfg = manager.load()
        assert cfg.presets["p1"]["entries"]["b"]["enabled"] is True
        assert cfg.presets["p1"]["entries"]["a"]["enabled"] is False


# ---------------------------------------------------------------------------
# Tests: select_preset
# ---------------------------------------------------------------------------


class TestSelectPreset:
    def test_select_changes_active_preset(self, manager: PresetConfigManager):
        manager.save(PresetConfig(active_preset_id="old", presets={}))
        manager.select_preset("new")
        cfg = manager.load()
        assert cfg.active_preset_id == "new"

    def test_select_persists(self, manager: PresetConfigManager, config_path: Path):
        manager.select_preset("p1")
        assert config_path.exists()
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert raw["activePresetId"] == "p1"


# ---------------------------------------------------------------------------
# Tests: merge with scan results
# ---------------------------------------------------------------------------


class TestMergeWithScan:
    def test_load_merges_entries_from_scanner(
        self, manager: PresetConfigManager, scanner_with_presets: PresetScanner, tmp_path: Path
    ):
        # Setup: save an empty config referencing a preset
        config_path = manager.config_path
        config_path.write_text(
            json.dumps(
                {
                    "activePresetId": "test-preset",
                    "presets": {
                        "test-preset": {
                            "source": "presets/test-preset.json",
                            "enabled": True,
                            "entries": {},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        # Inject fake scan results into the scanner
        fake_meta = make_meta(["e1", "e2", "e3"])
        scanner_with_presets.scan_all = lambda: [fake_meta]  # type: ignore[assignment]

        cfg = manager.load(scanner=scanner_with_presets)
        assert "test-preset" in cfg.presets
        entries = cfg.presets["test-preset"]["entries"]
        assert "e1" in entries
        assert "e2" in entries
        assert "e3" in entries
        # defaults: all enabled
        assert entries["e1"]["enabled"] is True
        assert entries["e2"]["enabled"] is True
        assert entries["e3"]["enabled"] is True

    def test_load_preserves_existing_enabled_states(
        self, manager: PresetConfigManager, scanner_with_presets: PresetScanner
    ):
        config_path = manager.config_path
        config_path.write_text(
            json.dumps(
                {
                    "activePresetId": "test-preset",
                    "presets": {
                        "test-preset": {
                            "source": "presets/test-preset.json",
                            "enabled": True,
                            "entries": {
                                "e1": {"enabled": True, "order": 1},
                                "e2": {"enabled": False, "order": 2},
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        fake_meta = make_meta(["e1", "e2", "e3"])
        scanner_with_presets.scan_all = lambda: [fake_meta]  # type: ignore[assignment]

        cfg = manager.load(scanner=scanner_with_presets)
        entries = cfg.presets["test-preset"]["entries"]
        # e1 / e2 keep their explicit states
        assert entries["e1"]["enabled"] is True
        assert entries["e2"]["enabled"] is False
        # e3 gets default from scanner
        assert entries["e3"]["enabled"] is True
        assert entries["e3"]["order"] == 100
