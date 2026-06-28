"""OpenCode TUI injection client.

OpenCode must be started with:
    opencode --port 4096
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


OC_URL = "http://127.0.0.1:4096"
DEFAULT_TIMEOUT = 300

# Ensure web-frontend modules are importable when running as a script.
WEB_ROOT = Path(__file__).resolve().parent
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from airp_context import get_active_preset_prompt  # noqa: E402


def check_oc_alive() -> bool:
    try:
        post("/tui/clear-prompt", timeout=2)
        return True
    except Exception:
        return False


def inject_message(text: str) -> None:
    post("/tui/clear-prompt", timeout=5)
    time.sleep(0.1)
    post("/tui/append-prompt", {"text": text}, timeout=10)
    time.sleep(0.1)
    post("/tui/submit-prompt", timeout=5)


def send_message(user_text: str, cwd: Path, timeout: int = DEFAULT_TIMEOUT) -> str:
    cwd = Path(cwd)
    response_file = cwd / "web-frontend" / "web-response.txt"
    response_file.unlink(missing_ok=True)
    rp_log = current_rp_log(cwd)
    previous_size = rp_log.stat().st_size if rp_log.exists() else 0
    prompt = build_prompt(user_text)
    inject_message(prompt)
    started = time.time()
    while time.time() - started <= timeout:
        if response_file.exists():
            text = response_file.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                response_file.unlink(missing_ok=True)
                return text
        if rp_log.exists() and rp_log.stat().st_size > previous_size:
            time.sleep(0.8)
            return read_new_log_text(rp_log, previous_size)
        time.sleep(1.2)
    raise TimeoutError(f"等待 OpenCode 回复超时: {timeout}s")


def build_prompt(user_text: str) -> str:
    preset_block = get_active_preset_prompt()
    header = (
        "[Web 前端 AIRP 输入]\n"
        "请严格按 AGENTS.md 的 OpenCode AIRP 规则处理这一轮。\n"
        "你需要读取 current-card.txt，使用对应角色卡、memory、variables 和世界书索引。\n"
        "请生成叙事回复；如有画面，保留 [img: english tags]；如需要更新变量，输出 <UpdateVariable> 块。\n"
        "最后把完整回复写入 web-frontend/web-response.txt，并追加到当前角色卡 rp-log.txt。\n\n"
    )
    if preset_block:
        header += f"{preset_block}\n\n"
    
    # Add relation suggestion prompt if configured
    try:
        import json
        from pathlib import Path
        settings_path = Path(__file__).resolve().parent / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text(encoding="utf-8", errors="replace"))
            relation_prompt = settings.get("relationPrompt")
            if relation_prompt:
                header += (
                    "[人脉分析]\n"
                    f"{relation_prompt}\n"
                    "如需输出新人脉，请在回复末尾加入 <RelationSuggestions>[\"角色名\", ...]</RelationSuggestions> 块。\n"
                    "也可以输出更详细的 JSON：<RelationSuggestions>[{\"name\":\"张三\",\"relation\":\"盟友\",\"desc\":\"描述\",\"favor\":0}, ...]</RelationSuggestions>\n\n"
                )
            user_name = (settings.get("userName") or "").strip()
            user_bio = (settings.get("userBio") or "").strip()
            if user_name or user_bio:
                header += "[用户信息]\n"
                if user_name:
                    header += f"用户名：{user_name}\n"
                if user_bio:
                    header += f"用户简介：{user_bio}\n"
                header += "\n"
    except Exception:
        pass

    # Sidebar structured blocks prompt
    header += (
        "[侧边栏数据]\n"
        "如需更新右侧目标/关键事件/资产，请在回复末尾加入对应 JSON 块：\n"
        "<Goals>[{\"id\":\"g1\",\"title\":\"目标名\",\"progress\":0-100}]</Goals>\n"
        "<Events>[{\"round\":1,\"title\":\"事件名\",\"desc\":\"描述\"}]</Events>\n"
        "<Assets>[{\"id\":\"a1\",\"icon\":\"📦\",\"name\":\"物品名\",\"desc\":\"描述\"}]</Assets>\n"
        "资产总量上限通过 Assets 块中的 totalCapacity 字段指定，如 {\"items\":[...],\"totalCapacity\":50}。\n\n"
    )
    
    header += "用户输入：\n"
    prompt = f"{header}{user_text}\n"
    try:
        log_path = WEB_ROOT / "preset-injection.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"--- build_prompt at {__import__('datetime').datetime.now().isoformat()} ---\n")
            f.write(f"preset_block_len={len(preset_block)}\n")
            f.write(f"prompt_len={len(prompt)}\n")
            f.write(preset_block[:500] + ("\n...[truncated]\n" if len(preset_block) > 500 else "\n"))
    except Exception:
        pass
    return prompt


def current_rp_log(cwd: Path) -> Path:
    current_file = cwd / "current-card.txt"
    card = current_file.read_text(encoding="utf-8", errors="replace").strip() if current_file.exists() else ""
    if not card:
        card = "example-card"
    path = cwd / "角色卡" / card / "rp-log.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def read_new_log_text(path: Path, offset: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        text = handle.read().strip()
    return text


def post(endpoint: str, data: dict | None = None, timeout: int = 10) -> str:
    req = urllib.request.Request(f"{OC_URL}{endpoint}", data=json.dumps(data or {}).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 OpenCode TUI API {OC_URL}: {exc}") from exc


if __name__ == "__main__":
    print(json.dumps({"ok": check_oc_alive(), "url": OC_URL}, ensure_ascii=False))
