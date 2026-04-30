"""Smoke checks for the MVU engine."""

from __future__ import annotations

from .mvu_engine import process_text


def smoke_check() -> dict:
    text = (
        '<UpdateVariable><JSONPatch>'
        '[{"op":"replace","path":"/player/hp","value":10},'
        '{"op":"delta","path":"/player/hp","value":5},'
        '{"op":"insert","path":"/items","value":"key"},'
        '{"op":"remove","path":"/missing"},'
        '{"op":"move","from":"/player/hp","path":"/player/hp2"}]'
        '</JSONPatch></UpdateVariable>{{getvar::player.hp2}}'
    )
    clean, variables, changes = process_text(text, {})
    return {"ok": clean == "15" and variables.get("player", {}).get("hp2") == 15, "clean": clean, "variables": variables, "changes": changes}
