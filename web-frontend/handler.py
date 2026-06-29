"""Chat log, MVU, and content rendering helpers."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
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
    suggest_relations_from_text,
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

ALLOWED_TAGS = {
    "details", "summary", "div", "span", "hr", "ul", "ol", "li", "p", "br",
    "b", "strong", "i", "em", "u", "s", "blockquote", "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td", "font", "h1", "h2", "h3",
    "h4", "h5", "h6", "a", "img", "del", "ins", "mark", "sub", "sup",
}
ALLOWED_ATTRS = {
    "style", "class", "id", "color", "bgcolor", "align", "width", "height",
    "href", "src", "alt", "title", "open",
}
SELF_CLOSING = {"br", "hr", "img", "input", "meta", "link"}
_JS_PROTOCOLS = ("javascript:", "data:", "vbscript:")


class HTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.result: list[str] = []
        self.tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return
        safe_attrs = _sanitize_attrs(attrs)
        attr_str = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        self.result.append(f"<{tag}{attr_str}>")
        if tag not in SELF_CLOSING:
            self.tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ALLOWED_TAGS and tag not in SELF_CLOSING:
            if self.tag_stack and self.tag_stack[-1] == tag:
                self.tag_stack.pop()
                self.result.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return
        safe_attrs = _sanitize_attrs(attrs)
        attr_str = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        self.result.append(f"<{tag}{attr_str}>")

    def handle_data(self, data: str) -> None:
        self.result.append(html.escape(data))

    def handle_comment(self, data: str) -> None:
        self.result.append(html.escape(f"<!--{data}-->"))

    def handle_decl(self, decl: str) -> None:
        self.result.append(html.escape(f"<!{decl}>"))

    def handle_pi(self, data: str) -> None:
        self.result.append(html.escape(f"<?{data}?>"))

    def unknown_decl(self, data: str) -> None:
        self.result.append(html.escape(f"<![{data}]>"))

    def get_html(self) -> str:
        return "".join(self.result)


def _sanitize_attrs(attrs: list[tuple[str, str | None]]) -> list[str]:
    safe: list[str] = []
    for k, v in attrs:
        k = k.lower()
        if k not in ALLOWED_ATTRS or v is None:
            continue
        if k in {"href", "src"}:
            v_lower = v.strip().lower()
            if v_lower and v_lower.startswith(_JS_PROTOCOLS):
                continue
        safe.append(f'{k}="{html.escape(v, quote=True)}"')
    return safe


def sanitize_html(text: str) -> str:
    if not text:
        return ""
    sanitizer = HTMLSanitizer()
    try:
        sanitizer.feed(text)
        return sanitizer.get_html()
    except Exception:
        return html.escape(text)


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
        # Extract goals / events / assets from AI output
        _apply_sidebar_blocks(content, card_id, get_card_dir(card_id))
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


def edit_message(message_id: str, new_content: str, card_id: str | None = None) -> bool:
    log = load_log(card_id)
    for entry in log:
        if entry.get("id") == message_id:
            entry["content"] = new_content
            entry["raw_content"] = new_content
            entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
            save_log(log, card_id)
            build_content_js(card_id)
            update_state(card_id)
            return True
    return False


def delete_message(message_id: str, card_id: str | None = None) -> bool:
    log = load_log(card_id)
    new_log = [entry for entry in log if entry.get("id") != message_id]
    if len(new_log) == len(log):
        return False
    save_log(new_log, card_id)
    build_content_js(card_id)
    update_state(card_id)
    return True


def backup_messages(messages: list | None = None, card_id: str | None = None) -> None:
    card_id = card_id or get_current_card_name()
    if messages is None:
        messages = load_log(card_id)
    card_dir = get_card_dir(card_id)
    backup_dir = card_dir / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"chat_backup_{ts}.json"
    atomic_write_json(path, messages)


def build_content_payload(card_id: str | None = None) -> dict:
    card_id = card_id or get_current_card_name()
    log = load_log(card_id) if card_id else []
    generated = safe_read_json(get_generated_map_path(card_id), {}) if card_id else {}
    html_parts = []
    image_prompts = []
    for index, entry in enumerate(log):
        role = entry.get("role", "user")
        entry_id = entry.get("id", f"msg_{index}")
        timestamp = format_time(entry.get("timestamp", ""))
        content = strip_mvu_blocks(entry.get("content", ""))
        menu_id = f"msg-menu-{entry_id}"
        is_user = role == "user"
        row_cls = "msg-row self" if is_user else "msg-row other"
        wrap_cls = "msg-wrap self" if is_user else "msg-wrap other"
        avatar_cls = "avatar self" if is_user else "avatar other"
        msg_cls = "msg self" if is_user else "msg other"
        avatar_label = "我" if is_user else "AI"

        if is_user:
            body = format_message(content)
            user_block = (
                f'<div class="{row_cls}" data-msg-id="{html.escape(entry_id)}">'
                f'<div class="{wrap_cls}">'
                f'<div class="{msg_cls}">{body}<div class="msg-more" style="float:right;cursor:pointer;font-size:12px;opacity:0.4;padding:0 6px;line-height:1" onclick="toggleMsgMenu(\'{menu_id}\', event)">...</div></div>'
                f'<div class="msg-menu" id="{menu_id}">'
                f'<button data-action="reroll">重新生成内容</button>'
                f'<button data-action="rollback">回滚</button>'
                f'<button data-action="backup">备份以上对话</button>'
                f'<button data-action="edit">编辑消息</button>'
                f'<button data-action="insert">插入消息</button>'
                f'<button data-action="delete">删除消息</button>'
                f'</div>'
                f'<div class="msg-time">{timestamp}</div>'
                f'</div>'
                f'<div class="{avatar_cls}">{avatar_label}</div>'
                f'</div>'
            )
            html_parts.append(user_block)
            continue

        segment = {"n": 0}
        image_buttons = []

        def repl(match: re.Match) -> str:
            key = f"{index}_{segment['n']}"
            segment["n"] += 1
            tags = match.group(1).strip()
            image_prompts.append({"key": key, "tags": tags, "turn": index})
            rel = generated.get(key)
            image_buttons.append(
                f'<button class="gen-btn msg-gen-btn" data-action="genimg" data-key="{html.escape(key)}" data-tags="{html.escape(tags, quote=True)}" '
                f'onclick="genImgPrompt(this)">生成插图</button>'
            )
            if rel:
                encoded = quote(str(rel), safe="/%")
                return f'<div class="gen-img-wrap" id="img-{key}"><img class="gen-img" src="/api/image?path={html.escape(encoded, quote=True)}" loading="lazy"></div>'
            return (
                f'<button class="gen-btn" data-key="{html.escape(key)}" data-tags="{html.escape(tags, quote=True)}" '
                f'onclick="genImgPrompt(this)">生成插图</button><div class="gen-img-wrap" id="img-{key}"></div>'
            )

        body = IMG_RE.sub(repl, format_message(content))
        if not image_buttons:
            auto_tags = _extract_image_tags(content)
            auto_key = f"auto_{index}"
            image_buttons.append(
                f'<button class="gen-btn msg-gen-btn" data-action="genimg" data-key="{html.escape(auto_key)}" data-tags="{html.escape(auto_tags, quote=True)}" '
                f'onclick="genImgPrompt(this)">生成插图</button>'
            )
        image_menu_buttons = "".join(image_buttons)
        assistant_block = (
            f'<div class="{row_cls}" data-msg-id="{html.escape(entry_id)}">'
            f'<div class="{avatar_cls}">{avatar_label}</div>'
            f'<div class="{wrap_cls}">'
            f'<div class="{msg_cls}">{body}<div class="msg-more" style="float:right;cursor:pointer;font-size:12px;opacity:0.4;padding:0 6px;line-height:1" onclick="toggleMsgMenu(\'{menu_id}\', event)">...</div></div>'
            f'<div class="msg-menu" id="{menu_id}">'
            f'<button data-action="reroll">重新生成内容</button>'
            f'<button data-action="rollback">回滚</button>'
            f'<button data-action="backup">备份以上对话</button>'
            f'<button data-action="edit">编辑消息</button>'
            f'<button data-action="insert">插入消息</button>'
            f'<button data-action="delete">删除消息</button>'
            f'{image_menu_buttons}'
            f'</div>'
            f'<div class="msg-time">{timestamp}</div>'
            f'</div>'
            f'</div>'
        )
        html_parts.append(assistant_block)

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


def _extract_image_tags(content: str, max_length: int = 80) -> str:
    """从消息内容中自动提取插图标签。"""
    if not content:
        return "illustration"
    text = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = ' '.join(text.split())
    return text[:max_length] if text else "illustration"


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
    # 优先读取 <options> 块
    block = re.search(r"<options>([\s\S]*?)</options>", text or "", re.IGNORECASE)
    source = block.group(1) if block else ""
    if source:
        for line in source.splitlines():
            clean = re.sub(r"<[^>]+>", "", line).strip(" -\t")
            if clean.startswith(">"):
                clean = clean[1:].strip()
            if clean and 6 <= len(clean) <= 80:
                options.append(clean)
    # 其次读取 <选项> 块（中文选项标签）
    if not options:
        option_block = re.search(r"<选项>([\s\S]*?)<!--选项-->", text or "", re.IGNORECASE)
        if option_block:
            block_content = option_block.group(1)
            for m in re.finditer(r"<(\d+)>([\s\S]*?)<!--\1-->", block_content):
                content = m.group(2).strip()
                clean = re.sub(r"<[^>]+>", "", content).strip()
                if clean and 4 <= len(clean) <= 120:
                    options.append(clean)
    # 其次读取 <xx> 块（编号行动选项）
    if not options:
        xx_block = re.search(r"<xx>([\s\S]*?)</xx>", text or "", re.IGNORECASE)
        if xx_block:
            for line in xx_block.group(1).splitlines():
                stripped = line.strip(" -\t")
                # 只保留以编号开头的行，跳过"请选择""下一步行动""提示"等标题行
                if not re.match(r"^\d+[\.\、\s]+", stripped):
                    continue
                clean = re.sub(r"<[^>]+>", "", stripped)
                clean = re.sub(r"^\d+[\.\、\s]+", "", clean).strip()
                if not clean:
                    continue
                if any(kw in clean for kw in ["下一步行动", "请选择", "提示", "Tips"]):
                    continue
                if 4 <= len(clean) <= 120:
                    options.append(clean)
    # 兜底：无序列表
    if not options and not block:
        for match in re.finditer(r"^\s*[-*]\s+(.{6,80})$", text or "", re.MULTILINE):
            options.append(match.group(1).strip())
    return options[:5]


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
        content = part['content']
        tag_map: dict[str, str] = {}
        def protect_tag(match: re.Match) -> str:
            key = f"__HTML_TAG_{len(tag_map)}__"
            tag_map[key] = match.group(0)
            return key
        protected = re.sub(r'<[^>]+>', protect_tag, content)
        protected = re.sub(r'["\u201c\u201d\u300c\u300d\u300e\u300f](.+?)["\u201c\u201d\u300c\u300d\u300e\u300f]', r'<span class="speaking">\1</span>', protected)
        protected = re.sub(r'【(.+?)】', r'<span class="narrator">\1</span>', protected)
        protected = re.sub(r"\*(.+?)\*", r"<em>\1</em>", protected)
        for key, tag in tag_map.items():
            protected = protected.replace(key, tag)
        content = sanitize_html(protected)
        output.append(content)
    return ''.join(output)


def format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%H:%M")
    except Exception:
        return ""


def _is_valid_character_name(name: str) -> bool:
    """Validate that a string looks like an actual person name, not a sentence fragment."""
    if not name or not (2 <= len(name) <= 6):
        return False
    # Reject names starting with sentence-initial particles/pronouns
    invalid_starts = {'但', '然', '于', '在', '你', '他', '她', '它', '这', '那', '如', '若', '又', '并', '且', '就', '才', '可', '虽', '尽', '我'}
    if name[0] in invalid_starts:
        return False
    # Reject abstract nouns and common words that are not names
    abstract_nouns = {'朋友', '敌人', '家人', '同学', '老师', '学生', '老板', '员工', '顾客',
                      '客人', '邻居', '陌生人', '路人', '保安', '服务员', '医生', '护士',
                      '警察', '记者', '记者', '司机', '业主', '住户'}
    if name in abstract_nouns:
        return False
    # Reject if ends with typical verb/sentence suffixes
    invalid_ends = {'了', '着', '过', '来', '去', '到', '在', '是', '的', '得', '地', '啊', '呢', '吗', '吧'}
    if name[-1] in invalid_ends:
        return False
    # Reject if contains obvious verb characters in the middle (sentence fragment indicator)
    common_verbs = {'说', '道', '问', '走', '站', '坐', '看', '想', '听', '叫', '笑', '叹',
                    '开', '关', '拿', '放', '打', '踢', '跑', '跳', '飞', '爬', '躺', '伏',
                    '抬', '低', '闭', '睁', '咬', '握', '环', '抱', '贴', '移', '扫', '瞥', '瞪', '盯',
                    '在', '给', '让', '被', '把', '向', '往', '从', '对', '为', '跟', '比'}
    for v in common_verbs:
        if v in name and len(name) <= 6:
            return False
    return True


def extract_relation_suggestions(text: str) -> list[dict]:
    """Extract relation suggestions from <RelationSuggestions> blocks in AI output."""
    if not text:
        return []
    suggestions = []
    pattern = re.compile(r'<RelationSuggestions>(.*?)</RelationSuggestions>', re.DOTALL | re.IGNORECASE)
    for m in pattern.finditer(text):
        try:
            raw = m.group(1).strip()
            # Support both ["name1", "name2"] and [{"name":"...", "desc":"..."}, ...]
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        name = item.strip().strip('"').strip("'")
                        if _is_valid_character_name(name):
                            suggestions.append({"name": name, "relation": "新角色", "favor": 0, "source": "ai"})
                    elif isinstance(item, dict):
                        name = str(item.get("name", "")).strip()
                        if _is_valid_character_name(name):
                            suggestions.append({
                                "name": name,
                                "relation": item.get("relation") or "新角色",
                                "favor": int(item.get("favor") or 0),
                                "desc": item.get("desc") or item.get("description") or "",
                                "source": "ai",
                            })
        except Exception:
            continue

    # Fallback: if no suggestions found from block, try simple name extraction
    if not suggestions:
        suggestions = suggest_relations_from_text(text)
        for s in suggestions:
            s["source"] = "ai"
        # Apply semantic filter to fallback results too
        suggestions = [s for s in suggestions if _is_valid_character_name(s.get("name", ""))]

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


# ---------------------------------------------------------------------------
# Sidebar block extraction: <Goals>, <Events>, <Assets>
# ---------------------------------------------------------------------------

def _apply_sidebar_blocks(text: str, card_id: str, card_dir: Path) -> None:
    """Parse structured sidebar blocks from AI output and persist to JSON."""
    goals = _extract_block(text, "Goals")
    events = _extract_block(text, "Events")
    assets = _extract_block(text, "Assets")
    try:
        if goals is not None:
            from card_store import save_goals
            save_goals(goals if isinstance(goals, list) else [], card_dir.name)
        if events is not None:
            from card_store import save_events
            save_events(events if isinstance(events, list) else [], card_dir.name)
        if assets is not None:
            from card_store import save_assets
            raw = assets if isinstance(assets, list) else []
            cap = 50
            if isinstance(assets, dict):
                raw = assets.get("items", raw)
                cap = int(assets.get("totalCapacity", 50) or 50)
            save_assets(raw, card_dir.name, cap)
    except Exception:
        pass


def _extract_block(text: str, tag: str) -> list | dict | None:
    """Extract JSON array/object from a <Tag>...</Tag> block."""
    pattern = re.compile(r"<" + tag + r">([\s\S]*?)</" + tag + r">", re.IGNORECASE)
    m = pattern.search(text or "")
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        data = json.loads(raw)
        return data
    except Exception:
        return None


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
