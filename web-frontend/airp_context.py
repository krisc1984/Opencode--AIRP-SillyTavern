"""Context inspection and worldbook matching for the Web bridge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from card_store import get_card_dir, get_card_payload, get_current_card_name, safe_read_json
from handler import load_log


WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent
CONTEXT_FILE = WEB_ROOT / "context-inspect.json"
SETTINGS_FILE = WEB_ROOT / "settings.json"
AIRP_ROOT = PROJECT_ROOT / "airp-sillytavern"

if str(AIRP_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRP_ROOT))

from runtime.match_worldbook import match_worldbook  # noqa: E402


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
        "metadata": {},
    }


def write_context(payload: dict) -> None:
    tmp = CONTEXT_FILE.with_name(CONTEXT_FILE.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONTEXT_FILE)
