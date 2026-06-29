"""Context inspection and worldbook matching for the Web bridge."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from card_store import get_card_dir, get_card_payload, get_current_card_name, safe_read_json
from handler import load_log
from preset_config import PresetConfigManager
from preset_scanner import PresetScanner

WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent
CONTEXT_FILE = WEB_ROOT / "context-inspect.json"
SETTINGS_FILE = WEB_ROOT / "settings.json"
AIRP_ROOT = PROJECT_ROOT / "airp-sillytavern"
PRESET_CONFIG_FILE = WEB_ROOT / "preset-config.json"

if str(AIRP_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRP_ROOT))

from runtime.match_worldbook import match_worldbook  # noqa: E402

preset_config_manager = PresetConfigManager(PRESET_CONFIG_FILE)


def _presets_dir() -> Path:
    """Return the presets directory, respecting AIRP_PRESETS_DIR env override."""
    env_dir = os.environ.get("AIRP_PRESETS_DIR")
    if env_dir:
        return Path(env_dir)
    return PROJECT_ROOT / "presets"


def _assemble_presets() -> dict[str, list[dict]]:
    """Scan the presets directory and return enabled entries grouped by preset name.

    Returns an empty dict if the presets directory does not exist or contains no
    valid preset files.

    User toggle choices from ``preset-config.json`` override the raw scanner
    ``enabled`` flag so that disabling an entry in the manager is respected at
    injection time.
    """
    presets_root = _presets_dir()
    if not presets_root.is_dir():
        return {}

    try:
        scanner = PresetScanner(presets_root)
        preset_groups = scanner.scan_all()
    except Exception:
        return {}

    # Load user toggle choices once. 结构: {preset_id: {entry_id: {enabled, ...}}}
    try:
        cfg = preset_config_manager.load()
        user_entries: dict[str, dict[str, dict[str, Any]]] = cfg.presets or {}
    except Exception:
        user_entries = {}

    assembled: dict[str, list[dict]] = {}
    for group in preset_groups:
        preset_name = group.name
        entries: list[dict] = []
        # ``user_entries[preset_id]`` is the preset metadata block whose ``entries``
        # key holds the per-entry toggle map.
        preset_user_map = (user_entries.get(group.id) or {}).get("entries") or {}
        for entry in group.entries:
            # User toggle takes precedence over the raw scanner flag.
            user_entry_cfg = preset_user_map.get(entry.id)
            if user_entry_cfg is not None and "enabled" in user_entry_cfg:
                entry_enabled = bool(user_entry_cfg["enabled"])
            else:
                entry_enabled = entry.enabled
            if not entry_enabled:
                continue
            entries.append(
                {
                    "id": entry.id,
                    "name": entry.name,
                    "role": entry.role,
                    "content": entry.content,
                    "injection_position": entry.injection_position,
                    "injection_depth": entry.injection_depth,
                    "injection_order": entry.injection_order,
                    "marker": entry.marker,
                    "forbid_overrides": entry.forbid_overrides,
                }
            )
        if entries:
            entries.sort(key=lambda item: item["injection_order"])
            assembled[preset_name] = entries
    return assembled


def get_active_preset_prompt() -> str:
    """Build a prompt fragment for the currently active preset.

    Returns an empty string if no preset is active or the active preset has no
    enabled entries.
    """
    cfg = preset_config_manager.load()
    active_id = cfg.active_preset_id
    if not active_id:
        return ""

    assembled = _assemble_presets()
    entries = assembled.get(active_id, [])
    if not entries:
        return ""

    parts = ["[活动预设]"]
    for entry in entries:
        role = entry.get("role", "system")
        name = entry.get("name", "")
        content = entry.get("content", "")
        if role == "system":
            parts.append(f"<系统>{name}: {content}")
        elif role == "user":
            parts.append(f"<用户>{name}: {content}")
        elif role == "assistant":
            parts.append(f"<助手>{name}: {content}")
        else:
            parts.append(f"<{role}>{name}: {content}")
    parts.append("[/活动预设]")
    return "\n".join(parts)


def ensure_context_file() -> None:
    if not CONTEXT_FILE.exists():
        write_context(default_context_payload())


def get_context_payload() -> dict:
    ensure_context_file()
    return safe_read_json(CONTEXT_FILE, default_context_payload())


def build_turn_context(user_message: str) -> dict:
    card_id = get_current_card_name()
    card_dir = get_card_dir(card_id)
    payload = build_context(card_id, user_message)
    payload["activatedLore"] = match_worldbook(card_dir, user_message, limit=3)
    payload["phase"] = "awaiting_response"
    write_context(payload)
    return payload


def finalize_turn_context(assistant_response: str) -> dict:
    payload = get_context_payload()
    payload["assistantResponse"] = assistant_response
    payload["phase"] = "completed"
    write_context(payload)
    return payload


def rebuild_context_snapshot() -> dict:
    card_id = get_current_card_name()
    payload = build_context(card_id, "")
    write_context(payload)
    return payload


def build_context(card_id: str, user_message: str) -> dict:
    card = get_card_payload(card_id)
    card_dir = get_card_dir(card_id)
    settings = safe_read_json(SETTINGS_FILE, {})
    history = load_log(card_id)[-12:]
    memory_dir = card_dir / "memory"
    memory = {}
    for name in ("project.md", "feedback.md", "user.md", "story_plan.md"):
        path = memory_dir / name
        memory[name] = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return {
        "ok": True,
        "cardId": card_id,
        "cardName": card["fields"].get("name") or card_id,
        "phase": "idle",
        "settings": settings,
        "userMessage": user_message,
        "assistantResponse": "",
        "history": history,
        "memory": memory,
        "activatedLore": [],
        "assembledPresets": _assemble_presets(),
        "metadata": {
            "historyTurns": len(history),
            "worldbookMode": "indexed",
            "tokenUsage": "unavailable",
        },
    }


def default_context_payload() -> dict:
    return {
        "ok": True,
        "cardId": "",
        "cardName": "",
        "phase": "idle",
        "settings": {},
        "userMessage": "",
        "assistantResponse": "",
        "history": [],
        "memory": {},
        "activatedLore": [],
        "assembledPresets": {},
        "metadata": {},
    }


def write_context(payload: dict) -> None:
    tmp = CONTEXT_FILE.with_name(CONTEXT_FILE.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONTEXT_FILE)
