"""
Runtime commands: /swipe, /regen, /continue, /inspect, /lore, /memory, etc.

Each command operates on session state and returns a result dict
that the SKILL.md orchestration layer uses to guide the model's response.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .state import SessionState, ChatHistory
from .tokenizer import count_tokens


class SwipeManager:
    """Stores alternate replies per turn for /swipe navigation."""

    def __init__(self, session_dir: str | Path = "session"):
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "swipes.json"
        self.data: dict[str, list[str]] = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def store(self, turn: int, content: str) -> int:
        """Store a swipe for a turn. Returns the swipe index."""
        key = str(turn)
        if key not in self.data:
            self.data[key] = []
        self.data[key].append(content)
        self.save()
        return len(self.data[key]) - 1

    def get(self, turn: int) -> list[str]:
        """Get all swipes for a turn."""
        return self.data.get(str(turn), [])

    def count(self, turn: int) -> int:
        return len(self.data.get(str(turn), []))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_swipe(state: SessionState, history: ChatHistory,
              swipes: SwipeManager) -> dict:
    """
    /swipe — Request an alternate reply.
    Returns context indicating the model should generate a new alternative
    from the same prompt state (before the last assistant message).
    """
    turn = state.get("turn", 0)
    last = history.get_last(role="assistant")
    if last:
        # Store current reply as a swipe before requesting new one
        swipes.store(turn, last["content"])
    existing = swipes.get(turn)
    return {
        "command": "swipe",
        "turn": turn,
        "existing_swipes": len(existing),
        "instruction": (
            "Generate a completely different alternative reply for the same "
            "prompt state. Do NOT repeat or paraphrase previous swipes. "
            "Previous alternatives exist — be creative and take a different approach."
        ),
        "previous_swipes_summary": [
            s[:100] + "..." if len(s) > 100 else s
            for s in existing[-3:]  # show last 3 for reference
        ],
    }


def cmd_regen(state: SessionState, history: ChatHistory) -> dict:
    """
    /regen — Rewrite the latest assistant turn from the same state.
    Removes the last assistant message from history.
    """
    last = history.pop_last()
    if last and last.get("role") != "assistant":
        # Oops, put it back — last message wasn't assistant
        history.append(**last)
        return {"command": "regen", "error": "Last message is not an assistant message."}

    return {
        "command": "regen",
        "removed": last["content"][:200] if last else None,
        "instruction": (
            "Rewrite the assistant's last reply. The previous version has been "
            "removed from history. Generate a fresh response."
        ),
    }


def cmd_continue(state: SessionState, history: ChatHistory) -> dict:
    """
    /continue — Extend the latest assistant turn without repeating its opening.
    """
    last = history.get_last(role="assistant")
    if not last:
        return {"command": "continue", "error": "No assistant message to continue."}

    return {
        "command": "continue",
        "last_content": last["content"],
        "instruction": (
            "Continue the assistant's last message seamlessly. "
            "Do NOT repeat any text from the existing message. "
            "Pick up exactly where it left off."
        ),
    }


def cmd_impersonate(state: SessionState, persona: dict) -> dict:
    """
    /impersonate — Draft a candidate user reply in {{user}} style.
    """
    user_name = persona.get("name", "User")
    return {
        "command": "impersonate",
        "user_name": user_name,
        "persona": persona.get("description", ""),
        "instruction": (
            f"Write ONE candidate reply as {user_name}. "
            f"Match their voice and personality. "
            f"Label it as a suggestion the user can accept, edit, or discard."
        ),
    }


def cmd_inspect(context_result: dict) -> dict:
    """
    /inspect — Show prompt assembly structure and activated lore.
    """
    meta = context_result.get("metadata", {})
    return {
        "command": "inspect",
        "context_limit": meta.get("context_limit"),
        "budget": meta.get("budget"),
        "total_used": meta.get("total_used"),
        "remaining": meta.get("remaining"),
        "blocks": meta.get("blocks", {}),
        "history_kept": meta.get("history_turns_kept"),
        "history_trimmed": meta.get("history_turns_total", 0) - meta.get("history_turns_kept", 0),
        "activated_lore": meta.get("activated_lore_names", []),
    }


def cmd_lore(entries: list[dict], query: str = "") -> dict:
    """
    /lore [term] — Show matching or all activated lore entries.
    """
    if query:
        matched = [
            {
                "uid": e.get("uid"),
                "key": e.get("key"),
                "comment": e.get("comment", ""),
                "constant": e.get("constant", False),
                "content_preview": e["content"][:200] if e.get("content") else "",
                "tokens": count_tokens(e.get("content", "")),
            }
            for e in entries
            if query.lower() in str(e.get("key", "")).lower()
            or query.lower() in e.get("content", "").lower()
            or query.lower() in e.get("comment", "").lower()
        ]
    else:
        matched = [
            {
                "uid": e.get("uid"),
                "key": e.get("key"),
                "comment": e.get("comment", ""),
                "activation": e.get("_activation", "inactive"),
                "tokens": count_tokens(e.get("content", "")),
            }
            for e in entries
        ]
    return {"command": "lore", "query": query, "entries": matched}


def cmd_memory(state: SessionState) -> dict:
    """
    /memory — Show current narrative state summary.
    """
    return {
        "command": "memory",
        "summary": state.summary(),
        "raw": state.to_dict(),
    }
