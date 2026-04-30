"""Post-generation quality helpers."""

from __future__ import annotations

import re


def check_reply(text: str, target_words: int = 600) -> dict:
    clean = re.sub(r"<[^>]+>", "", text or "")
    cjk = len(re.findall(r"[\u4e00-\u9fff]", clean))
    latin = len(re.findall(r"\b[a-zA-Z]+\b", clean))
    count = cjk + latin
    minimum = int(max(80, target_words * 0.8))
    return {
        "ok": count >= minimum,
        "count": count,
        "target": target_words,
        "minimum": minimum,
        "tokens": "unavailable",
    }
