"""
Structured session state management.

Maintains a JSON state file that tracks narrative state, turn counter,
and all bookkeeping that the model shouldn't be trusted to maintain alone.
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any


DEFAULT_STATE = {
    "turn": 0,
    "created_at": "",
    "updated_at": "",
    "char_name": "",
    "user_name": "",
    "time_in_story": "",
    "location": "",
    "active_characters": [],
    "mood": "",
    "inventory": [],
    "injuries": [],
    "relationships": {},
    "open_hooks": [],
    "secrets": [],
    "important_facts": [],
    "last_updated_turn": 0,
}


class SessionState:
    """Manages the structured narrative state for an AIRP session."""

    def __init__(self, session_dir: str | Path = "session"):
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"
        self.data: dict = self._load()

    def _load(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        state = DEFAULT_STATE.copy()
        state["created_at"] = _now()
        state["updated_at"] = _now()
        return state

    def save(self) -> None:
        self.data["updated_at"] = _now()
        self.state_path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def init(self, char_name: str, user_name: str, **kwargs) -> None:
        """Initialize state for a new session."""
        self.data["char_name"] = char_name
        self.data["user_name"] = user_name
        self.data["created_at"] = _now()
        for k, v in kwargs.items():
            if k in self.data:
                self.data[k] = v
        self.save()

    def next_turn(self) -> int:
        """Increment turn counter and save. Returns new turn number."""
        self.data["turn"] += 1
        self.save()
        return self.data["turn"]

    def update(self, **kwargs) -> None:
        """Update narrative state fields."""
        for k, v in kwargs.items():
            self.data[k] = v
        self.data["last_updated_turn"] = self.data["turn"]
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def summary(self) -> str:
        """Return a human-readable state summary for /memory command."""
        lines = [
            f"Turn: {self.data['turn']}",
            f"Character: {self.data.get('char_name', '?')}",
            f"User: {self.data.get('user_name', '?')}",
        ]
        if self.data.get("time_in_story"):
            lines.append(f"Story time: {self.data['time_in_story']}")
        if self.data.get("location"):
            lines.append(f"Location: {self.data['location']}")
        if self.data.get("mood"):
            lines.append(f"Mood: {self.data['mood']}")
        if self.data.get("active_characters"):
            lines.append(f"Present: {', '.join(self.data['active_characters'])}")
        if self.data.get("inventory"):
            lines.append(f"Inventory: {', '.join(self.data['inventory'])}")
        if self.data.get("injuries"):
            lines.append(f"Injuries: {', '.join(self.data['injuries'])}")
        if self.data.get("open_hooks"):
            lines.append("Open hooks:")
            for h in self.data["open_hooks"]:
                lines.append(f"  - {h}")
        if self.data.get("secrets"):
            lines.append("Secrets:")
            for s in self.data["secrets"]:
                lines.append(f"  - {s}")
        if self.data.get("important_facts"):
            lines.append("Important facts:")
            for f in self.data["important_facts"]:
                lines.append(f"  - {f}")
        if self.data.get("relationships"):
            lines.append("Relationships:")
            for name, rel in self.data["relationships"].items():
                lines.append(f"  - {name}: {rel}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return dict(self.data)


class ChatHistory:
    """Manages the chat history log as a JSON array."""

    def __init__(self, session_dir: str | Path = "session"):
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "history.json"
        self.messages: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.messages, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def append(self, role: str, content: str, **metadata) -> None:
        """Add a message to history."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": _now(),
        }
        entry.update(metadata)
        self.messages.append(entry)
        self.save()

    def pop_last(self) -> dict | None:
        """Remove and return the last message (for regen)."""
        if self.messages:
            msg = self.messages.pop()
            self.save()
            return msg
        return None

    def get_last(self, role: str | None = None) -> dict | None:
        """Get the last message, optionally filtered by role."""
        for msg in reversed(self.messages):
            if role is None or msg.get("role") == role:
                return msg
        return None

    def recent(self, n: int = 10) -> list[dict]:
        """Return last n messages."""
        return self.messages[-n:]

    def all(self) -> list[dict]:
        return list(self.messages)

    def count(self) -> int:
        return len(self.messages)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
