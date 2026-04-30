"""Lightweight memory updater for AIRP card folders."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def update_project_memory(card_dir: str | Path, user_text: str, assistant_text: str) -> dict:
    card_dir = Path(card_dir)
    memory = card_dir / "memory"
    memory.mkdir(exist_ok=True)
    project = memory / "project.md"
    existing = project.read_text(encoding="utf-8", errors="replace") if project.exists() else "# 剧情进度\n\n"
    stamp = datetime.now().isoformat(timespec="seconds")
    user_line = compact(user_text)
    assistant_line = compact(assistant_text)
    block = f"\n## {stamp}\n\n- 用户：{user_line}\n- 回复：{assistant_line}\n"
    # Keep the file bounded; recent memory is enough for this automatic updater.
    combined = existing + block
    lines = combined.splitlines()
    if len(lines) > 220:
        lines = lines[:20] + ["", "<!-- older automatic entries trimmed -->", ""] + lines[-180:]
    project.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"ok": True, "path": str(project)}


def compact(text: str, limit: int = 180) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(update_project_memory(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[3] if len(sys.argv) > 3 else ""), ensure_ascii=False))
