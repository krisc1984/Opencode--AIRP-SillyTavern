"""
World Info / Lorebook activation engine.

Scans chat history for keyword matches and returns activated entries
within a token budget. Handles constant entries, primary/secondary keys,
selective logic, probability, ordering, and recursive activation.
"""

from __future__ import annotations
import re
import random
from typing import Any
from .tokenizer import count_tokens


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def activate(
    entries: list[dict],
    chat_history: list[dict],
    scan_depth: int = 2,
    token_budget: int = 512,
    recursion_limit: int = 3,
    char_name: str = "",
    user_name: str = "",
) -> list[dict]:
    """
    Return entries that should be injected into context.

    Each returned entry has an extra ``_activation`` key describing why
    it was activated (``"constant"``, ``"key_match"``, ``"recursive"``).
    """
    if not entries:
        return []

    # Build scan window: last scan_depth * 2 messages (user+assistant pairs)
    window_msgs = chat_history[-(scan_depth * 2):] if chat_history else []
    scan_text = _build_scan_text(window_msgs, char_name, user_name)

    budget = token_budget
    activated: list[dict] = []
    activated_uids: set = set()

    # Phase 1: constant entries (always on)
    budget = _collect_constants(entries, activated, activated_uids, budget)

    # Phase 2: key-triggered entries
    budget = _collect_key_matches(
        entries, scan_text, activated, activated_uids, budget
    )

    # Phase 3: recursive activation
    for _ in range(recursion_limit):
        new_text = "\n".join(e["content"] for e in activated if e.get("_activation") != "constant")
        if not new_text:
            break
        new_count = _collect_key_matches(
            entries, new_text, activated, activated_uids, budget,
            activation_reason="recursive",
            exclude_no_recurse=True,
        )
        if new_count == budget:
            break  # nothing new activated
        budget = new_count

    return activated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_scan_text(messages: list[dict], char_name: str, user_name: str) -> str:
    """Concatenate message contents for scanning."""
    parts = []
    for msg in messages:
        prefix = ""
        role = msg.get("role", "")
        if role == "user":
            prefix = f"{user_name}: " if user_name else ""
        elif role == "assistant":
            prefix = f"{char_name}: " if char_name else ""
        parts.append(prefix + msg.get("content", ""))
    return "\n".join(parts)


def _matches_keys(entry: dict, text: str) -> bool:
    """Check if an entry's primary (and optionally secondary) keys match."""
    primary_keys = entry.get("key", [])
    if isinstance(primary_keys, str):
        primary_keys = [k.strip() for k in primary_keys.split(",") if k.strip()]

    if not primary_keys:
        return False

    case_sensitive = entry.get("caseSensitive", False)
    whole_words = entry.get("matchWholeWords", False)
    flags = 0 if case_sensitive else re.IGNORECASE

    primary_hit = False
    for key in primary_keys:
        if not key:
            continue
        pattern = re.escape(key)
        if whole_words:
            pattern = r'\b' + pattern + r'\b'
        if re.search(pattern, text, flags):
            primary_hit = True
            break

    if not primary_hit:
        return False

    # Secondary key logic (selective mode)
    if not entry.get("selective"):
        return True

    secondary_keys = entry.get("keysecondary", [])
    if isinstance(secondary_keys, str):
        secondary_keys = [k.strip() for k in secondary_keys.split(",") if k.strip()]

    if not secondary_keys:
        return True  # no secondary filter means pass

    sec_hit = False
    for key in secondary_keys:
        if not key:
            continue
        pattern = re.escape(key)
        if whole_words:
            pattern = r'\b' + pattern + r'\b'
        if re.search(pattern, text, flags):
            sec_hit = True
            break

    logic = entry.get("selectiveLogic", 0)
    if logic == 0:  # AND: both primary and secondary must match
        return sec_hit
    elif logic == 1:  # NOT: primary matches but secondary must NOT
        return not sec_hit
    else:  # ANY / OR
        return True  # primary already matched


def _passes_probability(entry: dict) -> bool:
    """Roll probability check."""
    if not entry.get("useProbability", True):
        return True
    prob = entry.get("probability", 100)
    if prob >= 100:
        return True
    return random.random() * 100 < prob


def _passes_sticky_cooldown(entry: dict) -> bool:
    """
    Placeholder for sticky/cooldown/delay tracking.
    Full implementation needs turn counter from state.
    Returns True for now (always passes).
    """
    # TODO: integrate with state.py turn tracking
    return True


def _entry_cost(entry: dict) -> int:
    return count_tokens(entry.get("content", ""))


def _collect_constants(
    entries: list[dict],
    activated: list[dict],
    seen: set,
    budget: int,
) -> int:
    """Collect constant entries. Returns remaining budget."""
    for entry in entries:
        uid = entry.get("uid", id(entry))
        if uid in seen:
            continue
        if not entry.get("constant") or entry.get("disable"):
            continue
        cost = _entry_cost(entry)
        if cost > budget:
            continue
        entry_copy = {**entry, "_activation": "constant"}
        activated.append(entry_copy)
        seen.add(uid)
        budget -= cost
    return budget


def _collect_key_matches(
    entries: list[dict],
    scan_text: str,
    activated: list[dict],
    seen: set,
    budget: int,
    activation_reason: str = "key_match",
    exclude_no_recurse: bool = False,
) -> int:
    """Collect key-matched entries sorted by order. Returns remaining budget."""
    candidates: list[tuple[int, dict]] = []

    for entry in entries:
        uid = entry.get("uid", id(entry))
        if uid in seen:
            continue
        if entry.get("disable") or entry.get("constant"):
            continue
        if exclude_no_recurse and entry.get("excludeRecursion"):
            continue
        if not _passes_probability(entry):
            continue
        if not _passes_sticky_cooldown(entry):
            continue
        if _matches_keys(entry, scan_text):
            order = entry.get("order", 100)
            candidates.append((order, entry))

    candidates.sort(key=lambda x: x[0])

    for _, entry in candidates:
        uid = entry.get("uid", id(entry))
        cost = _entry_cost(entry)
        if cost > budget:
            continue
        entry_copy = {**entry, "_activation": activation_reason}
        activated.append(entry_copy)
        seen.add(uid)
        budget -= cost

    return budget
