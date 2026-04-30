"""
Token counting with tiktoken fallback.
Tries tiktoken first; falls back to a heuristic that handles CJK properly.
"""

from __future__ import annotations
import re

_encoder = None
_USE_TIKTOKEN = False

try:
    import tiktoken
    _encoder = tiktoken.encoding_for_model("gpt-4o")
    _USE_TIKTOKEN = True
except Exception:
    pass

# CJK Unicode ranges for heuristic
_CJK_RE = re.compile(
    r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff'
    r'\U00020000-\U0002a6df\U0002a700-\U0002b73f'
    r'\U0002b740-\U0002b81f\U0002b820-\U0002ceaf'
    r'\U0002ceb0-\U0002ebef\U00030000-\U0003134f'
    r'\u3000-\u303f\uff00-\uffef]'
)


def count_tokens(text: str) -> int:
    """Return token count for a string."""
    if not text:
        return 0
    if _USE_TIKTOKEN:
        return len(_encoder.encode(text))
    return _heuristic_count(text)


def _heuristic_count(text: str) -> int:
    """
    Rough token estimate:
    - CJK characters ≈ 1 token each (sometimes 0.7, but overcount is safer)
    - Latin / whitespace ≈ 1 token per 4 chars
    """
    cjk_chars = len(_CJK_RE.findall(text))
    remaining = len(text) - cjk_chars
    return cjk_chars + max(remaining // 4, 1)


def count_messages(messages: list[dict]) -> int:
    """
    Count tokens for a list of chat messages.
    Adds per-message overhead (role, separators).
    """
    total = 0
    for msg in messages:
        total += 4  # <role> + separators overhead
        total += count_tokens(msg.get("content", ""))
        if msg.get("name"):
            total += count_tokens(msg["name"]) + 1
    total += 2  # reply priming
    return total


def count_block(label: str, content: str) -> dict:
    """Return a dict with label, content preview, and token count."""
    tokens = count_tokens(content)
    return {"label": label, "tokens": tokens, "chars": len(content)}


def using_tiktoken() -> bool:
    return _USE_TIKTOKEN
