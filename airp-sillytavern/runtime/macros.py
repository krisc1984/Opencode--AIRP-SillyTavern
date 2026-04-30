"""
Macro resolution for SillyTavern-style placeholders.
"""

from __future__ import annotations
import re
from datetime import datetime


def resolve(text: str, char_name: str, user_name: str,
            scenario: str = "", personality: str = "",
            original: str = "", extras: dict | None = None) -> str:
    """Replace all known macros in *text*."""
    if not text:
        return text

    replacements = {
        "{{char}}": char_name,
        "{{user}}": user_name,
        "{{scenario}}": scenario,
        "{{personality}}": personality,
        "{{original}}": original,
        "{{date}}": datetime.now().strftime("%Y-%m-%d"),
        "{{time}}": datetime.now().strftime("%H:%M"),
        "{{idle_duration}}": "",
        "{{random}}": "",
        "{{roll}}": "",
        "{{input}}": "",
    }
    if extras:
        for k, v in extras.items():
            replacements[f"{{{{{k}}}}}"] = str(v)

    result = text
    for macro, value in replacements.items():
        result = result.replace(macro, value)

    # Strip any remaining unresolved macros like {{outlet::X}}
    result = re.sub(r'\{\{outlet::[^}]*\}\}', '', result)
    return result


def resolve_dict(d: dict, **kwargs) -> dict:
    """Deep-resolve macros in all string values of a dict."""
    out = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = resolve(v, **kwargs)
        elif isinstance(v, dict):
            out[k] = resolve_dict(v, **kwargs)
        elif isinstance(v, list):
            out[k] = [
                resolve(item, **kwargs) if isinstance(item, str)
                else resolve_dict(item, **kwargs) if isinstance(item, dict)
                else item
                for item in v
            ]
        else:
            out[k] = v
    return out
