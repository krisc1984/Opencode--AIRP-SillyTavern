"""Chat log, MVU, and content rendering helpers."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote

from card_store import (
    atomic_write_json,
    get_card_dir,
    get_chat_log_path,
    get_current_card_name,
    get_generated_map_path,
    get_variables_path,
    safe_read_json,
)

import sys

AIRP_ROOT = Path(__file__).resolve().parent.parent / "airp-sillytavern"
if str(AIRP_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRP_ROOT))

from runtime.mvu_engine import process_text, strip_mvu_blocks  # noqa: E402
from runtime.write_memory import update_project_memory  # noqa: E402
from runtime.story_plan import maybe_update_story_plan  # noqa: E402


WEB_ROOT = Path(__file__).resolve().parent
CONTENT_JS = WEB_ROOT / "content.js"
STATE_JS = WEB_ROOT / "state.js"
IMG_RE = re.compile(r"\[img:\s*(.+?)\]", re.IGNORECASE)


def load_log(card_id: str | None = None) -> list[dict]:
    data = safe_read_json(get_chat_log_path(card_id), [])
    return normalize_entries(data if isinstance(data, list) else [])


def save_log(entries: list[dict], card_id: str | None = None) -> None:
    atomic_write_json(get_chat_log_path(card_id), normalize_entries(entries))


def append_message(role: str, content: str, card_id: str | None = None) -> dict:
    card_id = card_id or get_current_card_name()
    log = load_log(card_id)
    variables = safe_read_json(get_variables_path(card_id), {})
    raw_content = content or ""
    changes = {}
    relation_suggestions = []
    if role in {"assistant", "ai"}:
        content, variables, changes = process_text(raw_content, variables if isinstance(variables, dict) else {})
        atomic_write_json(get_variables_path(card_id), variables)
        # Extract relation suggestions from AI output
        relation_suggestions = extract_relation_suggestions(content)
        if relation_suggestions:
            try:
                from card_store import save_relation_suggestions
                save_relation_suggestions(relation_suggestions, card_id)
            except Exception:
                pass
    entry = {
        "id": uuid4().hex,
        "role": "assistant" if role == "ai" else role,
        "content": content,
        "raw_content": raw_content,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    if changes:
        entry["variables_delta"] = changes
    log.append(entry)
    save_log(log, card_id)
    if entry["role"] == "assistant":
        last_user = next((item.get("content", "") for item in reversed(log[:-1]) if item.get("role") == "user"), "")
        update_project_memory(get_card_dir(card_id), last_user, content)
        assistant_turns = len([item for item in log if item.get("role") == "assistant"])
        maybe_update_story_plan(get_card_dir(card_id), assistant_turns)
    build_content_js(card_id)
    update_state(card_id)
    return entry


def reroll_last(card_id: str | None = None) -> str:
    log = load_log(card_id)
    if len(log) < 2:
        return ""
    last_user = ""
    if log[-1].get("role") == "assistant":
        log.pop()
    if log and log[-1].get("role") == "user":
        last_user = log[-1].get("content", "")
        log.pop()
    save_log(log, card_id)
    build_content_js(card_id)
    update_state(card_id)
    return last_user


def rollback(from_index: int, card_id: str | None = None) -> None:
    log = load_log(card_id)
    save_log(log[:max(0, from_index)], card_id)
    build_content_js(card_id)
    update_state(card_id)


def build_content_payload(card_id: str | None = None) -> dict:
    card_id = card_id or get_current_card_name()
    log = load_log(card_id) if card_id else []
    generated = safe_read_json(get_generated_map_path(card_id), {}) if card_id else {}
    html_parts = []
    image_prompts = []
    for index, entry in enumerate(log):
        role = entry.get("role", "user")
        timestamp = format_time(entry.get("timestamp", ""))
        content = strip_mvu_blocks(entry.get("content", ""))
        if role == "user":
            html_parts.append(
                f'<div class="msg-row self"><div class="msg-wrap self">'
                f'<div class="msg self">{format_message(content)}</div><div class="msg-time">{timestamp}</div>'
                f'</div><div class="avatar self">我</div></div>'
            )
            continue
        segment = {"n": 0}

        def repl(match: re.Match) -> str:
            key = f"{index}_{segment['n']}"
            segment["n"] += 1
            tags = match.group(1).strip()
            image_prompts.append({"key": key, "tags": tags, "turn": index})
            rel = generated.get(key)
            if rel:
                encoded = quote(str(rel), safe="/%")
                return f'<div class="gen-img-wrap" id="img-{key}"><img class="gen-img" src="/api/image?path={html.escape(encoded, quote=True)}" loading="lazy"></div>'
            return (
                f'<button class="gen-btn" data-key="{html.escape(key)}" data-tags="{html.escape(tags, quote=True)}" '
                f'onclick="genImgPrompt(this)">生成插图</button><div class="gen-img-wrap" id="img-{key}"></div>'
            )

        body = IMG_RE.sub(repl, format_message(content))
        html_parts.append(
            f'<div class="msg-row other"><div class="avatar other">AI</div><div class="msg-wrap other">'
            f'<div class="msg other">{body}</div><div class="msg-time">{timestamp}</div></div></div>'
        )
    options = extract_options(log[-1].get("content", "")) if log and log[-1].get("role") == "assistant" else []
    return {
        "ok": True,
        "card": card_id,
        "html": "".join(html_parts),
        "options": options,
        "images": generated,
        "imagePrompts": image_prompts,
        "messages": len(log),
    }


def build_content_js(card_id: str | None = None) -> None:
    payload = build_content_payload(card_id)
    js = (
        f"var CONTENT_HTML = {json.dumps(payload['html'], ensure_ascii=False)};\n"
        f"var TURN_OPTIONS = {json.dumps(payload['options'], ensure_ascii=False)};\n"
        f"var IMG_GENERATED = {json.dumps(payload['images'], ensure_ascii=False)};\n"
    )
    atomic_text(CONTENT_JS, js)


def update_state(card_id: str | None = None) -> dict:
    card_id = card_id or get_current_card_name()
    log = load_log(card_id) if card_id else []
    variables = safe_read_json(get_variables_path(card_id), {}) if card_id else {}
    state = {
        "ok": True,
        "card": card_id,
        "messages": len(log),
        "assistantTurns": len([item for item in log if item.get("role") == "assistant"]),
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "variables": variables if isinstance(variables, dict) else {},
    }
    atomic_text(STATE_JS, "var STATE = " + json.dumps(state, ensure_ascii=False) + ";\n")
    return state


def normalize_entries(entries: list[dict]) -> list[dict]:
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role", "user")
        if role == "ai":
            role = "assistant"
        result.append({
            "id": entry.get("id") or uuid4().hex,
            "role": role,
            "content": entry.get("content", ""),
            "raw_content": entry.get("raw_content", entry.get("content", "")),
            "timestamp": entry.get("timestamp") or datetime.now().isoformat(timespec="seconds"),
            **({"variables_delta": entry["variables_delta"]} if "variables_delta" in entry else {}),
        })
    return result


def extract_options(text: str) -> list[str]:
    options = []
    block = re.search(r"<options>([\s\S]*?)</options>", text or "", re.IGNORECASE)
    source = block.group(1) if block else ""
    for line in source.splitlines():
        clean = re.sub(r"<[^>]+>", "", line).strip(" -\t")
        if clean.startswith(">"):
            clean = clean[1:].strip()
        if clean and 6 <= len(clean) <= 80:
            options.append(clean)
    if not options and not block:
        for match in re.finditer(r"^\s*[-*]\s+(.{6,80})$", text or "", re.MULTILINE):
            options.append(match.group(1).strip())
    return options[:4]


def format_message(text: str) -> str:
    if not text:
        return ""

    lines = text.split('\n')
    parts = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if (
            stripped.startswith('|')
            and stripped.endswith('|')
            and '|' in stripped[1:-1]
            and index + 1 < len(lines)
            and re.match(r'^\|[-:]+(?:\|[-:]+)*\|$', lines[index + 1].strip())
        ):
            rows = []
            cells = [cell.strip() for cell in stripped.split('|')[1:-1]]
            if cells and any(cells):
                rows.append(
                    '<tr>'
                    + ''.join(f'<th>{html.escape(cell)}</th>' for cell in cells)
                    + '</tr>'
                )
                index += 2
                while index < len(lines):
                    current = lines[index].strip()
                    if current.startswith('|') and current.endswith('|') and '|' in current[1:-1]:
                        cells = [cell.strip() for cell in current.split('|')[1:-1]]
                        if cells and any(cells):
                            rows.append(
                                '<tr>'
                                + ''.join(f'<td>{html.escape(cell)}</td>' for cell in cells)
                                + '</tr>'
                            )
                            index += 1
                        else:
                            break
                    else:
                        break
                parts.append('<table>' + ''.join(rows) + '</table>')
                continue
        parts.append(line)
        index += 1

    text_parts = []
    buffer = []
    for part in parts:
        if part.startswith('<table>'):
            if buffer:
                text_parts.append({'type': 'text', 'content': '\n'.join(buffer)})
                buffer = []
            text_parts.append({'type': 'table', 'content': part})
        else:
            buffer.append(part)
    if buffer:
        text_parts.append({'type': 'text', 'content': '\n'.join(buffer)})

    output = []
    for part in text_parts:
        if part['type'] == 'table':
            output.append(part['content'])
            continue
        escaped = html.escape(part['content'])
        escaped = re.sub(r'["\u201c\u201d\u300c\u300d\u300e\u300f](.+?)["\u201c\u201d\u300c\u300d\u300e\u300f]', r'<span class="speaking">\1</span>', escaped)
        escaped = re.sub(r'【(.+?)】', r'<span class="narrator">\1</span>', escaped)
        escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
        output.append(escaped.replace('\n', '<br>'))
    return ''.join(output)


def format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%H:%M")
    except Exception:
        return ""


def extract_relation_suggestions(text: str) -> list[dict]:
    """Extract relation suggestions from <RelationSuggestions> blocks in AI output."""
    if not text:
        return []
    suggestions = []
    pattern = re.compile(r'<RelationSuggestions>(.*?)</RelationSuggestions>', re.DOTALL | re.IGNORECASE)
    for m in pattern.finditer(text):
        try:
            raw = m.group(1).strip()
            names = json.loads(raw)
            if isinstance(names, list):
                for name in names:
                    name = str(name).strip()
                    if name and 2 <= len(name) <= 10:
                        suggestions.append({"name": name, "relation": "新角色", "favor": 0, "source": "ai"})
        except Exception:
            continue
    return suggestions[:10]


def atomic_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def bridge_done() -> None:
    try:
        import urllib.request

        urllib.request.urlopen("http://127.0.0.1:8765/api/done", data=b"{}", timeout=2)
    except Exception:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("append")
    p.add_argument("role")
    p.add_argument("text")
    sub.add_parser("rebuild")
    sub.add_parser("done")
    args = parser.parse_args()
    if args.cmd == "append":
        append_message(args.role, args.text)
    elif args.cmd == "rebuild":
        build_content_js()
        update_state()
    elif args.cmd == "done":
        bridge_done()
