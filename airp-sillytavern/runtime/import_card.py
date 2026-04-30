"""Import SillyTavern cards and prepare per-card AIRP runtime files.

This module is intentionally standard-library only. It accepts a card folder
that may contain a SillyTavern JSON card, PNG card, standalone world book JSON
files, or plain text material, then creates the normalized runtime layout used
by the OpenCode bridge.
"""

from __future__ import annotations

import base64
import json
import re
import struct
from datetime import datetime
from pathlib import Path
from typing import Any


CARD_DEFAULTS = {
    "name": "",
    "description": "",
    "personality": "",
    "scenario": "",
    "first_mes": "",
    "mes_example": "",
    "creator_notes": "",
    "system_prompt": "",
    "post_history_instructions": "",
    "alternate_greetings": [],
    "character_book": {"entries": []},
    "tags": [],
    "creator": "",
    "character_version": "1.0",
    "extensions": {},
}


WORLD_ENTRY_DEFAULTS = {
    "uid": 0,
    "id": None,
    "comment": "",
    "key": [],
    "keysecondary": [],
    "content": "",
    "constant": False,
    "selective": False,
    "selectiveLogic": 0,
    "order": 100,
    "position": 1,
    "disable": False,
    "excludeRecursion": False,
    "preventRecursion": False,
    "probability": 100,
    "useProbability": True,
    "depth": 0,
    "role": 0,
    "group": "",
    "groupOverride": False,
    "groupWeight": 100,
    "scanDepth": None,
    "caseSensitive": False,
    "matchWholeWords": False,
    "automationId": "",
    "sticky": 0,
    "cooldown": 0,
    "delay": 0,
}


def import_card_dir(card_dir: str | Path, project_root: str | Path | None = None) -> dict:
    """Normalize one card directory and create its runtime files."""
    card_dir = Path(card_dir)
    project_root = Path(project_root) if project_root else card_dir.parent.parent
    card_dir.mkdir(parents=True, exist_ok=True)

    card_data, source = load_card_material(card_dir)
    card_data = normalize_card(card_data)
    fields = extract_card_fields(card_data)
    entries = collect_worldbook_entries(card_data, card_dir, source_file=source.get("path"))

    worldbook = {"entries": entries}
    ensure_runtime_dirs(card_dir)
    atomic_json(card_dir / "card.json", card_data)
    atomic_json(card_dir / "worldbooks" / "main.json", worldbook)
    atomic_json(card_dir / "openings.json", build_openings(fields))
    ensure_json(card_dir / "chat_log.json", [])
    ensure_json(card_dir / "variables.json", load_initial_variables(card_data, entries))
    ensure_json(card_dir / "img_generated.json", {})
    ensure_text(card_dir / "rp-log.txt", "")
    ensure_text(card_dir / "session-state.md", initial_session_state(fields))
    memory_stats = write_memory_files(card_dir, fields, entries)

    return {
        "ok": True,
        "cardId": card_dir.name,
        "cardName": fields.get("name") or card_dir.name,
        "source": source,
        "worldbookEntries": len(entries),
        "openings": len(build_openings(fields)),
        "memory": memory_stats,
        "projectRoot": str(project_root),
    }


def load_card_material(card_dir: Path) -> tuple[dict, dict]:
    """Find and load primary card material from a directory."""
    png_files = sorted([p for p in card_dir.glob("*.png") if p.is_file()])
    for path in png_files:
        parsed = parse_png_card(path)
        if parsed:
            return parsed, {"type": "png", "path": str(path)}

    json_files = sorted([p for p in card_dir.glob("*.json") if p.is_file() and not p.name.startswith(".")])
    preferred = [p for p in json_files if p.name.lower() == "card.json"] + json_files
    seen: set[Path] = set()
    for path in preferred:
        if path in seen:
            continue
        seen.add(path)
        data = read_json(path, default=None)
        if isinstance(data, dict) and is_card_like(data):
            return data, {"type": "json", "path": str(path)}

    txt_files = sorted([p for p in card_dir.glob("*.txt") if p.is_file()])
    if txt_files:
        text = "\n\n".join(p.read_text(encoding="utf-8", errors="replace") for p in txt_files)
        return {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {**CARD_DEFAULTS, "name": card_dir.name, "first_mes": text.strip()},
        }, {"type": "txt", "path": str(txt_files[0])}

    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {**CARD_DEFAULTS, "name": card_dir.name, "first_mes": ""},
    }, {"type": "empty", "path": ""}


def parse_png_card(path: str | Path) -> dict | None:
    """Parse SillyTavern PNG tEXt/chara or tEXt/ccv3 chunks."""
    path = Path(path)
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        chunk_type = data[pos:pos + 4].decode("ascii", errors="replace")
        pos += 4
        chunk_data = data[pos:pos + length]
        pos += length + 4
        if chunk_type not in {"tEXt", "iTXt"}:
            continue
        keyword, text = _split_png_text(chunk_data, chunk_type)
        if keyword not in {"chara", "ccv3"} or not text:
            continue
        for candidate in (text, _maybe_urlsafe_b64(text)):
            try:
                decoded = base64.b64decode(candidate)
                return json.loads(decoded.decode("utf-8"))
            except Exception:
                continue
    return None


def normalize_card(data: dict) -> dict:
    if data.get("spec") == "chara_card_v2" and isinstance(data.get("data"), dict):
        normalized = json.loads(json.dumps(data, ensure_ascii=False))
        normalized["data"] = {**CARD_DEFAULTS, **normalized.get("data", {})}
        normalized["data"]["character_book"] = normalized["data"].get("character_book") or {"entries": []}
        return normalized
    source = data.get("data", data) if isinstance(data.get("data"), dict) else data
    fields = {**CARD_DEFAULTS}
    for key in CARD_DEFAULTS:
        if key in source:
            fields[key] = source.get(key)
    if "character_book" in data and not fields.get("character_book"):
        fields["character_book"] = data["character_book"]
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": fields}


def extract_card_fields(card_data: dict) -> dict:
    data = card_data.get("data", card_data)
    fields = {**CARD_DEFAULTS}
    for key in CARD_DEFAULTS:
        if key in data:
            fields[key] = data.get(key)
    if not isinstance(fields.get("alternate_greetings"), list):
        fields["alternate_greetings"] = []
    if isinstance(fields.get("tags"), str):
        fields["tags"] = [x.strip() for x in fields["tags"].split(",") if x.strip()]
    elif not isinstance(fields.get("tags"), list):
        fields["tags"] = []
    return fields


def collect_worldbook_entries(card_data: dict, card_dir: Path, source_file: str | None = None) -> list[dict]:
    """Merge embedded and sidecar world books, preserving entry content."""
    entries: list[dict] = []
    seen: set[str] = set()

    def add_many(raw_entries: Any) -> None:
        for entry in normalize_worldbook_entries(raw_entries):
            key = str(entry.get("id") or entry.get("uid") or entry.get("comment") or len(entries))
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)

    data = card_data.get("data", card_data)
    add_many((data.get("character_book") or {}).get("entries", []))

    candidates = list((card_dir / "worldbooks").glob("*.json")) if (card_dir / "worldbooks").exists() else []
    candidates += [p for p in card_dir.glob("*.json") if p.is_file() and str(p) != str(source_file)]
    for path in sorted(candidates, key=lambda p: p.name.lower()):
        raw = read_json(path, default={})
        if not isinstance(raw, dict):
            continue
        if is_card_like(raw):
            add_many((raw.get("data", raw).get("character_book") or {}).get("entries", []))
        elif "entries" in raw:
            add_many(raw.get("entries", []))
    return entries


def normalize_worldbook_entries(entries: Any) -> list[dict]:
    if isinstance(entries, dict):
        iterable = []
        for uid, entry in entries.items():
            if isinstance(entry, dict):
                item = dict(entry)
                item.setdefault("uid", uid)
                iterable.append(item)
    elif isinstance(entries, list):
        iterable = [e for e in entries if isinstance(e, dict)]
    else:
        iterable = []

    normalized = []
    for index, entry in enumerate(iterable):
        merged = {**WORLD_ENTRY_DEFAULTS, **entry}
        merged["uid"] = safe_int(merged.get("uid"), safe_int(merged.get("id"), index))
        merged["key"] = ensure_list(merged.get("key", merged.get("keys", [])))
        merged["keysecondary"] = ensure_list(merged.get("keysecondary", []))
        merged["comment"] = str(merged.get("comment") or merged.get("name") or f"Entry {merged['uid']}")
        merged["content"] = str(merged.get("content") or "")
        merged["order"] = safe_int(merged.get("order"), 100)
        merged["position"] = safe_int(merged.get("position"), 1)
        normalized.append(merged)
    return normalized


def build_openings(fields: dict) -> list[dict]:
    openings = []
    first = fields.get("first_mes") or ""
    if first.strip():
        openings.append({"id": 0, "label": make_label(first, "默认开场"), "content": first, "source": "first_mes"})
    for idx, text in enumerate(fields.get("alternate_greetings") or [], start=1):
        if str(text).strip():
            openings.append({"id": idx, "label": make_label(str(text), f"备选开场 {idx}"), "content": str(text), "source": "alternate_greetings"})
    return openings


def write_memory_files(card_dir: Path, fields: dict, entries: list[dict]) -> dict:
    memory = card_dir / "memory"
    memory.mkdir(exist_ok=True)
    reference_parts = []
    user_parts = []
    index = []
    for entry in entries:
        title = entry.get("comment") or f"Entry {entry.get('uid')}"
        content = entry.get("content", "")
        if not content.strip():
            continue
        block = f"## {title}\n\n{content.rstrip()}\n\n"
        if "{{user}}" in title or "{{user}}" in content:
            user_parts.append(block)
        else:
            reference_parts.append(block)
        keys = entry.get("key") or []
        index.append({
            "uid": entry.get("uid"),
            "title": title,
            "keys": keys,
            "keyword": keys[0] if keys else title,
            "section": f"## {title}",
            "one_liner": first_line(content),
        })

    atomic_text(memory / "reference.md", frontmatter("世界书与固定设定", "reference") + "".join(reference_parts))
    atomic_text(memory / "user.md", frontmatter("用户角色设定", "user") + "".join(user_parts))
    ensure_text(memory / "feedback.md", frontmatter("用户偏好", "feedback") + "# 用户偏好\n\n- 暂无。\n")
    ensure_text(memory / "project.md", frontmatter("剧情进度", "project") + "# 剧情进度\n\n- 等待开场。\n")
    ensure_text(memory / "story_plan.md", frontmatter("剧情规划", "story_plan") + "# 剧情规划\n\n- next_plan_at: 8\n- 暂无长期规划。\n")
    atomic_json(memory / ".worldbook_index.json", index)
    atomic_text(memory / "MEMORY.md", build_memory_index(fields, len(reference_parts), len(user_parts), len(index)))
    return {"reference": len(reference_parts), "user": len(user_parts), "index": len(index)}


def load_initial_variables(card_data: dict, entries: list[dict]) -> dict:
    data = card_data.get("data", card_data)
    variables = data.get("extensions", {}).get("tavern_helper", {}).get("variables", {})
    if isinstance(variables, dict) and variables:
        return variables
    for entry in entries:
        content = entry.get("content", "")
        if "[initvar]" not in entry.get("comment", "").lower() and "<initvar" not in content.lower():
            continue
        parsed = extract_json_block(content)
        if isinstance(parsed, dict):
            return parsed
    return {}


def initial_session_state(fields: dict) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    return (
        "# Session State\n\n"
        f"- updated_at: {now}\n"
        f"- character: {fields.get('name') or '未命名角色'}\n"
        "- scene: waiting\n"
        "- location: unknown\n"
        "- open_hooks: []\n"
    )


def ensure_runtime_dirs(card_dir: Path) -> None:
    for name in ("worldbooks", "memory", "generated"):
        (card_dir / name).mkdir(parents=True, exist_ok=True)


def is_card_like(data: dict) -> bool:
    if data.get("spec") == "chara_card_v2":
        return True
    source = data.get("data", data)
    return isinstance(source, dict) and ("first_mes" in source or "description" in source or "personality" in source) and "entries" not in data


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_json(path: Path, data: Any) -> None:
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def ensure_json(path: Path, data: Any) -> None:
    if not path.exists():
        atomic_json(path, data)


def ensure_text(path: Path, text: str) -> None:
    if not path.exists():
        atomic_text(path, text)


def ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def make_label(text: str, fallback: str) -> str:
    clean = re.sub(r"\s+", " ", strip_mvu(text)).strip()
    return clean[:28] if clean else fallback


def strip_mvu(text: str) -> str:
    text = re.sub(r"<UpdateVariable>[\s\S]*?</UpdateVariable>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<initvar>[\s\S]*?</initvar>", "", text, flags=re.IGNORECASE)
    return text.strip()


def first_line(text: str, limit: int = 80) -> str:
    clean = re.sub(r"<[^>]+>", "", text or "").strip()
    line = next((x.strip() for x in clean.splitlines() if x.strip()), "")
    return line[:limit]


def frontmatter(name: str, type_name: str) -> str:
    return f"---\nname: {name}\ntype: {type_name}\n---\n\n"


def build_memory_index(fields: dict, ref_count: int, user_count: int, index_count: int) -> str:
    return (
        "# 记忆索引\n\n"
        f"- character: {fields.get('name') or '未命名'}\n"
        f"- reference.md: {ref_count} 条世界书/固定设定\n"
        f"- user.md: {user_count} 条用户角色设定\n"
        f"- .worldbook_index.json: {index_count} 条检索索引\n"
        "- project.md: 剧情进度\n"
        "- feedback.md: 用户偏好\n"
        "- story_plan.md: 长期剧情规划\n"
    )


def extract_json_block(text: str) -> Any:
    match = re.search(r"<initvar[^>]*>([\s\S]*?)</initvar>", text, re.IGNORECASE)
    raw = match.group(1).strip() if match else text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        return None


def _split_png_text(chunk_data: bytes, chunk_type: str) -> tuple[str, str]:
    if chunk_type == "tEXt":
        null = chunk_data.find(b"\x00")
        if null < 0:
            return "", ""
        return (
            chunk_data[:null].decode("latin-1", errors="replace"),
            chunk_data[null + 1:].decode("latin-1", errors="replace"),
        )
    null = chunk_data.find(b"\x00")
    if null < 0:
        return "", ""
    keyword = chunk_data[:null].decode("utf-8", errors="replace")
    # iTXt layout: keyword\0 compression_flag compression_method language\0 translated\0 text
    rest = chunk_data[null + 1:]
    parts = rest.split(b"\x00", 3)
    text = parts[-1].decode("utf-8", errors="replace") if parts else ""
    return keyword, text


def _maybe_urlsafe_b64(text: str) -> str:
    return text.replace("-", "+").replace("_", "/") + ("=" * (-len(text) % 4))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import one AIRP card directory")
    parser.add_argument("card_dir")
    parser.add_argument("project_root", nargs="?")
    args = parser.parse_args()
    print(json.dumps(import_card_dir(args.card_dir, args.project_root), ensure_ascii=False, indent=2))
