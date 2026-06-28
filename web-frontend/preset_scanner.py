"""
Preset scanner — walks presets/ and parses SillyTavern preset JSON files.

This module intentionally has no dependency on the rest of the app so it
can be imported by tests, the web server, and the AIRP context builder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresetEntry:
    id: str
    name: str
    role: str  # system | user | assistant
    content: str
    marker: bool
    enabled: bool
    injection_position: int
    injection_depth: int
    injection_order: int
    forbid_overrides: bool
    source_file: str
    preset_name: str


@dataclass
class PresetMeta:
    id: str
    name: str
    source: Path
    entries: list[PresetEntry] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

_AUXILIARY_KEYWORDS = ("regex", "quickreply", "qr", "快速回复")


class PresetScanner:
    """Recursively scans a directory for SillyTavern preset JSON files."""

    def __init__(self, presets_dir: str | Path | None = None) -> None:
        if presets_dir is None:
            # Default to <project_root>/presets
            presets_dir = Path(__file__).resolve().parent.parent / "presets"
        self.presets_dir = Path(presets_dir)

    def scan_all(self) -> list[PresetMeta]:
        """Return parsed preset metadata for every valid preset file found."""
        if not self.presets_dir.exists():
            return []

        results: list[PresetMeta] = []
        for json_file in sorted(self.presets_dir.rglob("*.json")):
            if self._is_auxiliary(json_file):
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict):
                continue

            preset = self._parse_preset(data, json_file)
            results.append(preset)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_auxiliary(self, path: Path) -> bool:
        """Heuristic: skip regex / quickreply companion files."""
        name = path.name.lower()
        return any(kw in name for kw in _AUXILIARY_KEYWORDS)

    def _parse_preset(self, data: dict, source: Path) -> PresetMeta:
        name = str(data.get("name") or source.stem)
        params = self._extract_params(data)
        entries = self._extract_entries(data, source)
        return PresetMeta(
            id=source.stem,
            name=name,
            source=source,
            entries=entries,
            params=params,
        )

    def _extract_params(self, data: dict) -> dict[str, Any]:
        sampling_keys = (
            "temperature",
            "top_p",
            "top_k",
            "min_p",
            "frequency_penalty",
            "presence_penalty",
            "repetition_penalty",
            "max_tokens",
            "context_limit",
            "stream",
        )
        return {k: data[k] for k in sampling_keys if k in data}

    def _extract_entries(self, data: dict, source: Path) -> list[PresetEntry]:
        prompts = data.get("prompts")
        if not isinstance(prompts, list):
            return []

        entries: list[PresetEntry] = []
        for idx, p in enumerate(prompts):
            if not isinstance(p, dict):
                continue

            entries.append(
                PresetEntry(
                    id=f"{source.stem}_{idx}",
                    name=str(p.get("name") or f"Entry {idx}"),
                    role=str(p.get("role", "system")),
                    content=str(p.get("content", "")),
                    marker=bool(p.get("marker", False)),
                    enabled=bool(p.get("enabled", True)),
                    injection_position=int(p.get("injection_position", 0)),
                    injection_depth=int(p.get("injection_depth", 4)),
                    injection_order=int(p.get("injection_order", 100)),
                    forbid_overrides=bool(p.get("forbid_overrides", False)),
                    source_file=str(source),
                    preset_name=str(data.get("name") or source.stem),
                )
            )
        return entries
