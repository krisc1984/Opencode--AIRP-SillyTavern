"""Small MVU engine for SillyTavern-style variable updates."""

from __future__ import annotations

import copy
import json
import re
from typing import Any


UPDATE_RE = re.compile(r"<UpdateVariable>[\s\S]*?</UpdateVariable>", re.IGNORECASE)
JSON_PATCH_RE = re.compile(r"<JSONPatch>\s*(?:```(?:json)?\s*)?([\s\S]*?)(?:```\s*)?</JSONPatch>", re.IGNORECASE)
LEGACY_PATCH_RE = re.compile(r"<json_?patch>\s*(?:```(?:json)?\s*)?([\s\S]*?)(?:```\s*)?</json_?patch>", re.IGNORECASE)


def strip_mvu_blocks(text: str) -> str:
    text = UPDATE_RE.sub("", text or "")
    text = LEGACY_PATCH_RE.sub("", text)
    return text.strip()


def extract_json_patches(text: str) -> list[dict]:
    patches: list[dict] = []
    for block in UPDATE_RE.findall(text or ""):
        patches.extend(_patches_from_matches(JSON_PATCH_RE.findall(block)))
    outside_update_blocks = UPDATE_RE.sub("", text or "")
    patches.extend(_patches_from_matches(LEGACY_PATCH_RE.findall(outside_update_blocks)))
    return patches


def apply_patches(variables: dict, patches: list[dict]) -> tuple[dict, dict]:
    data = copy.deepcopy(variables or {})
    changes: dict[str, dict] = {}
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        op = str(patch.get("op") or "").lower()
        path = pointer_to_parts(str(patch.get("path") or ""))
        if op in {"replace", "add"}:
            old = deep_get(data, path)
            deep_set(data, path, patch.get("value"))
            changes[parts_to_label(path)] = {"old": old, "new": patch.get("value"), "op": op}
        elif op == "delta":
            old = deep_get(data, path, 0)
            value = patch.get("value", 0)
            if isinstance(old, (int, float)) and isinstance(value, (int, float)):
                new = old + value
                deep_set(data, path, new)
                changes[parts_to_label(path)] = {"old": old, "new": new, "op": op}
        elif op == "insert":
            old = copy.deepcopy(deep_get(data, path))
            insert_value(data, path, patch.get("value"))
            changes[parts_to_label(path)] = {"old": old, "new": deep_get(data, path), "op": op}
        elif op == "remove":
            old = deep_get(data, path)
            deep_delete(data, path)
            changes[parts_to_label(path)] = {"old": old, "new": None, "op": op}
        elif op == "move":
            from_path = pointer_to_parts(str(patch.get("from") or ""))
            old = deep_get(data, from_path)
            deep_delete(data, from_path)
            deep_set(data, path, old)
            changes[parts_to_label(path)] = {"old": None, "new": old, "op": op, "from": parts_to_label(from_path)}
    return data, changes


def render_templates(text: str, variables: dict) -> str:
    def getvar(match: re.Match) -> str:
        value = deep_get(variables, dotted_to_parts(match.group(1).strip()), "(未定义)")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def formatvar(match: re.Match) -> str:
        value = deep_get(variables, dotted_to_parts(match.group(1).strip()), "(未定义)")
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, indent=2)

    text = re.sub(r"\{\{getvar::([^}]+)\}\}", getvar, text or "")
    text = re.sub(r"\{\{formatvar::([^}]+)\}\}", formatvar, text)
    return text


def process_text(text: str, variables: dict) -> tuple[str, dict, dict]:
    patches = extract_json_patches(text)
    new_variables, changes = apply_patches(variables, patches)
    clean = render_templates(strip_mvu_blocks(text), new_variables)
    return clean, new_variables, changes


def _patches_from_matches(matches: list[str]) -> list[dict]:
    patches = []
    for raw in matches:
        try:
            parsed = json.loads(raw.strip())
        except Exception:
            continue
        if isinstance(parsed, list):
            patches.extend([p for p in parsed if isinstance(p, dict)])
        elif isinstance(parsed, dict):
            patches.append(parsed)
    return patches


def pointer_to_parts(path: str) -> list[str | int]:
    if not path:
        return []
    if path.startswith("/"):
        raw = path[1:].split("/")
        parts: list[str | int] = []
        for item in raw:
            item = item.replace("~1", "/").replace("~0", "~")
            parts.append(int(item) if item.isdigit() else item)
        return parts
    return dotted_to_parts(path)


def dotted_to_parts(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for piece in re.finditer(r"([^.[]+)|\[(\d+)\]", path):
        value = piece.group(1) if piece.group(1) is not None else piece.group(2)
        parts.append(int(value) if str(value).isdigit() and piece.group(2) is not None else value)
    return parts


def parts_to_label(parts: list[str | int]) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + part
    return out or "(root)"


def deep_get(data: Any, parts: list[str | int], default: Any = None) -> Any:
    cur = data
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and isinstance(part, int) and 0 <= part < len(cur):
            cur = cur[part]
        else:
            return default
    return cur


def deep_set(data: dict, parts: list[str | int], value: Any) -> None:
    if not parts:
        if isinstance(value, dict):
            data.clear()
            data.update(value)
        return
    cur: Any = data
    for index, part in enumerate(parts[:-1]):
        nxt = parts[index + 1]
        if isinstance(cur, dict):
            if part not in cur or not isinstance(cur[part], (dict, list)):
                cur[part] = [] if isinstance(nxt, int) else {}
            cur = cur[part]
        elif isinstance(cur, list) and isinstance(part, int):
            while len(cur) <= part:
                cur.append({} if not isinstance(nxt, int) else [])
            cur = cur[part]
    last = parts[-1]
    if isinstance(cur, list) and isinstance(last, int):
        while len(cur) <= last:
            cur.append(None)
        cur[last] = value
    elif isinstance(cur, dict):
        cur[last] = value


def insert_value(data: dict, parts: list[str | int], value: Any) -> None:
    existing = deep_get(data, parts)
    if isinstance(existing, list):
        existing.append(value)
    elif isinstance(existing, dict) and isinstance(value, dict):
        existing.update(value)
    elif existing is None:
        deep_set(data, parts, [value])


def deep_delete(data: Any, parts: list[str | int]) -> None:
    if not parts:
        if isinstance(data, dict):
            data.clear()
        return
    parent = deep_get(data, parts[:-1])
    last = parts[-1]
    if isinstance(parent, dict):
        parent.pop(last, None)
    elif isinstance(parent, list) and isinstance(last, int) and 0 <= last < len(parent):
        parent.pop(last)


if __name__ == "__main__":
    sample = '<UpdateVariable><JSONPatch>[{"op":"replace","path":"/hp","value":9},{"op":"delta","path":"/hp","value":1}]</JSONPatch></UpdateVariable>{{getvar::hp}}'
    print(process_text(sample, {"hp": 3}))
