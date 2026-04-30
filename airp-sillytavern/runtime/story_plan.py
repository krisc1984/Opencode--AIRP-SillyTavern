"""Simple story-plan updater.

The model remains responsible for creative planning. This module only keeps a
stable planning file so long sessions have a place to record direction.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def maybe_update_story_plan(card_dir: str | Path, turn: int, interval: int = 8) -> dict:
    card_dir = Path(card_dir)
    if turn <= 0 or turn % interval != 0:
        return {"ok": True, "updated": False, "reason": "not_due"}
    memory = card_dir / "memory"
    memory.mkdir(exist_ok=True)
    plan = memory / "story_plan.md"
    project = memory / "project.md"
    project_tail = tail(project.read_text(encoding="utf-8", errors="replace") if project.exists() else "", 40)
    text = (
        "---\nname: 剧情规划\ntype: story_plan\n"
        f"updated_at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"next_plan_at: {turn + interval}\n---\n\n"
        "# 剧情规划\n\n"
        f"- 当前轮次：{turn}\n"
        "- 自动提示：请在下一轮生成前参考最近剧情，保持伏笔、角色状态和节奏连续。\n\n"
        "## 最近剧情摘录\n\n"
        f"{project_tail}\n"
    )
    plan.write_text(text, encoding="utf-8")
    return {"ok": True, "updated": True, "path": str(plan)}


def tail(text: str, lines: int) -> str:
    return "\n".join(text.splitlines()[-lines:])
