"""
Preset configuration manager — persists user toggle/reorder choices.

File layout: ``web-frontend/preset-config.json``

Example:
    {
        "activePresetId": "preset-1",
        "presets": {
            "preset-1": {
                "source": "presets/preset-1.json",
                "enabled": true,
                "entries": {
                    "preset-1_0": { "enabled": true, "order": 1 },
                    "preset-1_1": { "enabled": false, "order": 2 }
                }
            }
        }
    }
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PresetConfig:
    active_preset_id: str = ""
    presets: dict[str, dict[str, Any]] = field(default_factory=dict)


class PresetConfigManager:
    """Read/write the preset configuration file."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).resolve().parent / "preset-config.json"
        self.config_path = Path(config_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, scanner: Any = None) -> PresetConfig:
        """Load config from disk, merging scanner results when provided."""
        raw = self._read_raw()
        cfg = PresetConfig(
            active_preset_id=str(raw.get("activePresetId") or ""),
            presets=copy.deepcopy(raw.get("presets") or {}),
        )

        if scanner is not None:
            self._merge_scanner_results(cfg, scanner)

        return cfg

    def save(self, config: PresetConfig) -> None:
        """Persist config to disk."""
        payload = {
            "activePresetId": config.active_preset_id,
            "presets": config.presets,
        }
        self.config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def toggle_entry(self, preset_id: str, entry_id: str, enabled: bool) -> dict:
        """Toggle a single entry's enabled flag and persist."""
        cfg = self.load()
        block = cfg.presets.setdefault(preset_id, {})
        entries = block.setdefault("entries", {})
        entries.setdefault(entry_id, {})
        entries[entry_id]["enabled"] = enabled
        self.save(cfg)
        return dict(entries[entry_id])

    def reorder_entries(self, preset_id: str, ordered_ids: list[str]) -> dict[str, dict]:
        """Reorder entries within a preset and persist."""
        cfg = self.load()
        block = cfg.presets.setdefault(preset_id, {})
        entries = block.setdefault("entries", {})

        # Re-key preserving existing flags
        new_entries: dict[str, Any] = {}
        for idx, eid in enumerate(ordered_ids, start=1):
            new_entries[eid] = {**entries.get(eid, {}), "order": idx}
        block["entries"] = new_entries
        self.save(cfg)
        return dict(new_entries)

    def select_preset(self, preset_id: str) -> None:
        """Switch the active preset and persist."""
        cfg = self.load()
        cfg.active_preset_id = preset_id
        self.save(cfg)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_raw(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _merge_scanner_results(self, cfg: PresetConfig, scanner: Any) -> None:
        """Fill in missing entries/defaults from scanner scan results."""
        try:
            scan_results = scanner.scan_all()
        except Exception:
            return

        for meta in scan_results:
            block = cfg.presets.setdefault(meta.id, {})
            block.setdefault("source", str(meta.source))
            block.setdefault("enabled", True)
            entries = block.setdefault("entries", {})

            for entry in meta.entries:
                if entry.id not in entries:
                    entries[entry.id] = {
                        "enabled": entry.enabled,
                        "order": entry.injection_order,
                    }
