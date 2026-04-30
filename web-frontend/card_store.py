"""Card storage helpers for the OpenCode AIRP bridge."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent
CARDS_DIR = PROJECT_ROOT / "角色卡"
CURRENT_CARD_FILE = PROJECT_ROOT / "current-card.txt"
AIRP_ROOT = PROJECT_ROOT / "airp-sillytavern"

if str(AIRP_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRP_ROOT))

from runtime.import_card import (  # noqa: E402
    CARD_DEFAULTS,
    atomic_json,
    build_openings,
    extract_card_fields,
    import_card_dir,
    normalize_card,
    normalize_worldbook_entries,
    read_json,
)


def list_available_card_ids() -> list[str]:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    ids = []
    for path in sorted(CARDS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir():
            continue
        if any(path.glob("card.json")) or any(path.glob("*.png")) or any(path.glob("*.json")) or any(path.glob("*.txt")):
            ids.append(path.name)
    return ids


def get_current_card_name() -> str:
    if CURRENT_CARD_FILE.exists():
        name = CURRENT_CARD_FILE.read_text(encoding="utf-8", errors="replace").strip()
        if name:
            return name
    cards = list_available_card_ids()
    if cards:
        CURRENT_CARD_FILE.write_text(cards[0], encoding="utf-8")
        return cards[0]
    return ""


def set_current_card_name(card_id: str) -> None:
    card_dir = get_card_dir(card_id)
    if not card_dir.exists():
        raise FileNotFoundError(f"角色卡不存在: {card_id}")
    ensure_card_runtime(card_id)
    CURRENT_CARD_FILE.write_text(card_id, encoding="utf-8")


def get_card_dir(card_id: str | None = None) -> Path:
    name = card_id or get_current_card_name()
    if not name:
        raise FileNotFoundError("没有可用角色卡")
    return CARDS_DIR / name


def ensure_card_runtime(card_id: str | None = None) -> dict:
    card_dir = get_card_dir(card_id)
    return import_card_dir(card_dir, PROJECT_ROOT)


def list_cards() -> list[dict]:
    active = get_current_card_name()
    cards = []
    for card_id in list_available_card_ids():
        try:
            ensure_card_runtime(card_id)
            payload = get_card_payload(card_id)
            chat = read_json(get_chat_log_path(card_id), [])
            cards.append({
                "id": card_id,
                "name": payload["fields"].get("name") or card_id,
                "active": card_id == active,
                "format": payload["format"],
                "messages": len(chat) if isinstance(chat, list) else 0,
                "updatedAt": mtime_iso(get_card_dir(card_id) / "card.json"),
            })
        except Exception as exc:
            cards.append({"id": card_id, "name": card_id, "active": card_id == active, "error": str(exc)})
    return cards


def get_card_payload(card_id: str | None = None) -> dict:
    card_dir = get_card_dir(card_id)
    ensure_card_runtime(card_dir.name)
    raw = read_json(card_dir / "card.json", {})
    raw = normalize_card(raw if isinstance(raw, dict) else {})
    return {
        "id": card_dir.name,
        "path": str(card_dir / "card.json"),
        "format": raw.get("spec", "chara_card_v2"),
        "raw": raw,
        "fields": extract_card_fields(raw),
    }


def save_card_fields(card_id: str, fields: dict) -> dict:
    payload = get_card_payload(card_id)
    raw = payload["raw"]
    data = raw.setdefault("data", {})
    for key in CARD_DEFAULTS:
        if key in fields:
            value = fields[key]
            if key == "tags" and isinstance(value, str):
                value = [x.strip() for x in value.split(",") if x.strip()]
            data[key] = value
    atomic_json(get_card_dir(card_id) / "card.json", raw)
    atomic_json(get_card_dir(card_id) / "openings.json", build_openings(extract_card_fields(raw)))
    ensure_card_runtime(card_id)
    return get_card_payload(card_id)


def get_chat_log_path(card_id: str | None = None) -> Path:
    return get_card_dir(card_id) / "chat_log.json"


def get_variables_path(card_id: str | None = None) -> Path:
    return get_card_dir(card_id) / "variables.json"


def get_generated_map_path(card_id: str | None = None) -> Path:
    return get_card_dir(card_id) / "img_generated.json"


def list_worldbooks(card_id: str | None = None) -> list[dict]:
    card_dir = get_card_dir(card_id)
    ensure_card_runtime(card_dir.name)
    result = []
    for path in sorted((card_dir / "worldbooks").glob("*.json"), key=lambda p: p.name.lower()):
        entries = normalize_worldbook_entries(read_json(path, {}).get("entries", []))
        result.append({"id": path.stem, "name": path.stem, "entries": len(entries), "updatedAt": mtime_iso(path)})
    return result


def get_worldbook_payload(book_name: str = "main", card_id: str | None = None) -> dict:
    card_dir = get_card_dir(card_id)
    ensure_card_runtime(card_dir.name)
    path = card_dir / "worldbooks" / f"{book_name or 'main'}.json"
    raw = read_json(path, {"entries": []})
    entries = normalize_worldbook_entries(raw.get("entries", []) if isinstance(raw, dict) else [])
    return {"cardId": card_dir.name, "id": path.stem, "path": str(path), "entries": entries, "raw": raw}


def save_worldbook_entries(book_name: str, entries: list[dict], card_id: str | None = None) -> dict:
    card_dir = get_card_dir(card_id)
    normalized = normalize_worldbook_entries(entries)
    path = card_dir / "worldbooks" / f"{book_name or 'main'}.json"
    atomic_json(path, {"entries": normalized})
    ensure_card_runtime(card_dir.name)
    return get_worldbook_payload(path.stem, card_dir.name)


def get_openings(card_id: str | None = None) -> list[dict]:
    card_dir = get_card_dir(card_id)
    ensure_card_runtime(card_dir.name)
    data = read_json(card_dir / "openings.json", [])
    return data if isinstance(data, list) else []


def switch_opening(opening_id: int, card_id: str | None = None) -> dict:
    openings = get_openings(card_id)
    selected = next((item for item in openings if int(item.get("id", -1)) == int(opening_id)), None)
    if not selected:
        raise FileNotFoundError(f"开场白不存在: {opening_id}")
    card = get_card_dir(card_id)
    atomic_json(card / "chat_log.json", [{
        "id": f"opening-{selected['id']}",
        "role": "assistant",
        "content": selected.get("content", ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": "opening",
    }])
    return selected


def preview_worldbook_activation(text: str, book_name: str = "main", card_id: str | None = None) -> dict:
    payload = get_worldbook_payload(book_name, card_id)
    text_l = (text or "").lower()
    matches = []
    for entry in payload["entries"]:
        keys = entry.get("key") or []
        hit = next((key for key in keys if key and key.lower() in text_l), "")
        if entry.get("constant") or hit:
            matches.append({
                "uid": entry.get("uid"),
                "comment": entry.get("comment"),
                "keys": keys,
                "reason": "constant" if entry.get("constant") else f"key:{hit}",
            })
    return {"book": payload["id"], "matches": matches[:10]}


def safe_read_json(path: Path, default: Any) -> Any:
    return read_json(path, default)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_json(path, data)


def mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except Exception:
        return ""
