"""Keyword worldbook matching against per-card memory indexes."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def match_worldbook(card_dir: str | Path, text: str, limit: int = 3) -> list[dict]:
    card_dir = Path(card_dir)
    memory = card_dir / "memory"
    index = read_json(memory / ".worldbook_index.json", [])
    if not isinstance(index, list):
        return []
    text_l = (text or "").lower()
    scored = []
    for item in index:
        keys = [item.get("keyword", ""), item.get("title", ""), *(item.get("keys") or [])]
        score = 0
        hits = []
        for key in keys:
            key_s = str(key).strip()
            if key_s and key_s.lower() in text_l:
                score += max(1, len(key_s))
                hits.append(key_s)
        if score:
            scored.append((score, item, hits))
    scored.sort(key=lambda row: row[0], reverse=True)
    reference = (memory / "reference.md").read_text(encoding="utf-8", errors="replace") if (memory / "reference.md").exists() else ""
    results = []
    for score, item, hits in scored[:limit]:
        content = extract_section(reference, item.get("section") or f"## {item.get('title', '')}")
        results.append({
            "title": item.get("title", ""),
            "keyword": item.get("keyword", ""),
            "hits": hits,
            "score": score,
            "section": item.get("section", ""),
            "content": content,
        })
    return results


def extract_section(markdown: str, heading: str) -> str:
    if not markdown or not heading:
        return ""
    escaped = re.escape(heading.strip())
    match = re.search(rf"^{escaped}\s*$([\s\S]*?)(?=^##\s|\Z)", markdown, re.MULTILINE)
    return match.group(0).strip() if match else ""


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


if __name__ == "__main__":
    card = sys.argv[1]
    text = " ".join(sys.argv[2:])
    print(json.dumps(match_worldbook(card, text), ensure_ascii=False, indent=2))
