"""
Artifact loader — classifies and validates SillyTavern JSON artifacts.

Detects presets, character cards, world books, and personas by shape,
validates required fields, and normalizes to a consistent internal format.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Shape detection
# ---------------------------------------------------------------------------

def classify(data: dict) -> str | None:
    """
    Classify a JSON object as one of:
      'preset', 'character', 'worldbook', 'persona', 'group', 'unknown'
    Returns None if not a dict.
    """
    if not isinstance(data, dict):
        return None

    # Character card V2
    if data.get("spec") == "chara_card_v2" or (
        "data" in data and isinstance(data["data"], dict)
        and "name" in data["data"] and "first_mes" in data["data"]
    ):
        return "character"

    # Legacy character card
    if all(k in data for k in ("name", "description", "first_mes")):
        return "character"

    # Preset — has prompt blocks or sampling config
    preset_keys = {"prompts", "prompt_order", "chat_completion_source"}
    sampling_keys = {"temperature", "top_p", "frequency_penalty", "presence_penalty"}
    if len(preset_keys & set(data.keys())) >= 2:
        return "preset"
    if "prompts" in data and "prompt_order" in data:
        return "preset"
    if len(sampling_keys & set(data.keys())) >= 3 and ("openai_model" in data or "max_tokens" in data):
        return "preset"

    # World book
    if "entries" in data and isinstance(data["entries"], (list, dict)):
        sample = None
        entries = data["entries"]
        if isinstance(entries, dict):
            sample = next(iter(entries.values()), None)
        elif isinstance(entries, list) and entries:
            sample = entries[0]
        if sample and isinstance(sample, dict):
            wb_keys = {"key", "keys", "content", "constant", "order", "position"}
            if len(wb_keys & set(sample.keys())) >= 2:
                return "worldbook"

    # Persona
    if "name" in data and "description" in data and "first_mes" not in data:
        return "persona"

    return "unknown"


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_character(data: dict) -> dict:
    """Normalize a character card to V2 format."""
    if data.get("spec") == "chara_card_v2":
        return data

    # Legacy → V2
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "personality": data.get("personality", ""),
            "scenario": data.get("scenario", ""),
            "first_mes": data.get("first_mes", ""),
            "mes_example": data.get("mes_example", ""),
            "creator_notes": data.get("creator_notes", ""),
            "system_prompt": data.get("system_prompt", ""),
            "post_history_instructions": data.get("post_history_instructions", ""),
            "alternate_greetings": data.get("alternate_greetings", []),
            "character_book": data.get("character_book", None),
            "tags": data.get("tags", []),
            "creator": data.get("creator", ""),
            "character_version": data.get("character_version", "1.0"),
            "extensions": data.get("extensions", {}),
        },
    }


def normalize_worldbook(data: dict) -> dict:
    """Normalize a world book to a consistent format with list entries."""
    entries = data.get("entries", [])

    # If entries is a dict (keyed by uid), convert to list
    if isinstance(entries, dict):
        entry_list = []
        for uid, entry in entries.items():
            entry.setdefault("uid", int(uid) if str(uid).isdigit() else hash(uid))
            entry_list.append(entry)
        entries = entry_list

    # Normalize individual entries
    normalized = []
    for i, entry in enumerate(entries):
        norm = {
            "uid": entry.get("uid", i),
            "key": _ensure_list(entry.get("key", entry.get("keys", []))),
            "keysecondary": _ensure_list(entry.get("keysecondary", [])),
            "comment": entry.get("comment", ""),
            "content": entry.get("content", ""),
            "constant": entry.get("constant", False),
            "selective": entry.get("selective", False),
            "selectiveLogic": entry.get("selectiveLogic", 0),
            "order": entry.get("order", 100),
            "position": entry.get("position", 1),
            "disable": entry.get("disable", False),
            "excludeRecursion": entry.get("excludeRecursion", False),
            "preventRecursion": entry.get("preventRecursion", False),
            "probability": entry.get("probability", 100),
            "useProbability": entry.get("useProbability", True),
            "depth": entry.get("depth", 0),
            "role": entry.get("role", 0),
            "group": entry.get("group", ""),
            "groupOverride": entry.get("groupOverride", False),
            "groupWeight": entry.get("groupWeight", 100),
            "scanDepth": entry.get("scanDepth", None),
            "caseSensitive": entry.get("caseSensitive", False),
            "matchWholeWords": entry.get("matchWholeWords", False),
            "automationId": entry.get("automationId", ""),
            "sticky": entry.get("sticky", 0),
            "cooldown": entry.get("cooldown", 0),
            "delay": entry.get("delay", 0),
        }
        normalized.append(norm)

    return {"entries": normalized}


def normalize_preset(data: dict) -> dict:
    """Extract useful preset settings into a clean dict."""
    return {
        "main_prompt": _find_main_prompt(data),
        "auxiliary_prompt": _find_aux_prompt(data),
        "post_history_instructions": _find_jailbreak(data),
        "context_limit": data.get("openai_max_context", data.get("context_limit", 8192)),
        "max_tokens": data.get("openai_max_tokens", data.get("max_tokens", 300)),
        "temperature": data.get("temperature", 1.0),
        "top_p": data.get("top_p", 1.0),
        "frequency_penalty": data.get("frequency_penalty", 0),
        "presence_penalty": data.get("presence_penalty", 0),
        "scan_depth": data.get("wi_scan_depth", 2),
        "wi_budget": data.get("wi_budget", 512),
        "stream": data.get("stream_openai", True),
        "raw": data,  # keep original for reference
    }


def normalize_persona(data: dict) -> dict:
    """Normalize persona to a clean dict."""
    return {
        "name": data.get("name", "User"),
        "description": data.get("description", ""),
        "position": data.get("position", "prompt_manager"),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_list(val: Any) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [k.strip() for k in val.split(",") if k.strip()]
    return []


def _find_main_prompt(preset: dict) -> str:
    """Extract main system prompt from a SillyTavern preset."""
    # Check prompts array
    for p in preset.get("prompts", []):
        if isinstance(p, dict):
            ident = p.get("identifier", p.get("name", ""))
            if ident == "main" or ident == "nsfw":
                if p.get("content"):
                    return p["content"]
    return preset.get("main_prompt", "")


def _find_aux_prompt(preset: dict) -> str:
    for p in preset.get("prompts", []):
        if isinstance(p, dict):
            ident = p.get("identifier", p.get("name", ""))
            if ident in ("nsfw", "auxiliaryPrompt", "jailbreak"):
                if p.get("content"):
                    return p["content"]
    return preset.get("auxiliary_prompt", "")


def _find_jailbreak(preset: dict) -> str:
    for p in preset.get("prompts", []):
        if isinstance(p, dict):
            ident = p.get("identifier", p.get("name", ""))
            if ident in ("jailbreak", "postHistoryInstructions"):
                if p.get("content"):
                    return p["content"]
    return preset.get("post_history_instructions", "")


# ---------------------------------------------------------------------------
# Multi-artifact intake
# ---------------------------------------------------------------------------

def intake(sources: list[dict | str | Path]) -> dict:
    """
    Process multiple JSON sources (dicts, JSON strings, or file paths).
    Returns a dict of classified and normalized artifacts.
    """
    result = {
        "preset": None,
        "character": None,
        "worldbook": None,
        "persona": None,
        "unknown": [],
        "errors": [],
    }

    for source in sources:
        try:
            data = _parse_source(source)
        except Exception as e:
            result["errors"].append(str(e))
            continue

        kind = classify(data)

        if kind == "character":
            result["character"] = normalize_character(data)
            # Check for embedded character book
            char_data = result["character"].get("data", {})
            if char_data.get("character_book") and not result["worldbook"]:
                result["worldbook"] = normalize_worldbook(char_data["character_book"])
        elif kind == "preset":
            result["preset"] = normalize_preset(data)
        elif kind == "worldbook":
            result["worldbook"] = normalize_worldbook(data)
        elif kind == "persona":
            result["persona"] = normalize_persona(data)
        else:
            result["unknown"].append(data)

    return result


def _parse_source(source) -> dict:
    if isinstance(source, dict):
        return source
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            return json.loads(text)
        # Try parsing as JSON string
        return json.loads(str(source))
    raise ValueError(f"Unsupported source type: {type(source)}")
