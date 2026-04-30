#!/usr/bin/env python3
"""OpenCode AIRP Web bridge server."""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from uuid import uuid4

from airp_context import build_turn_context, finalize_turn_context, get_context_payload, rebuild_context_snapshot
from card_store import (
    CARDS_DIR,
    PROJECT_ROOT,
    atomic_write_json,
    get_card_dir,
    get_card_payload,
    get_current_card_name,
    get_generated_map_path,
    get_openings,
    get_worldbook_payload,
    list_cards,
    list_worldbooks,
    preview_worldbook_activation,
    safe_read_json,
    save_card_fields,
    save_worldbook_entries,
    set_current_card_name,
    switch_opening,
)
from handler import append_message, build_content_js, build_content_payload, reroll_last, rollback, update_state


WEB_ROOT = Path(__file__).resolve().parent
PID_FILE = WEB_ROOT / "server.pid"
PORT_FILE = WEB_ROOT / "server-port.txt"
INPUT_FILE = WEB_ROOT / "web-input.txt"
PENDING_FILE = WEB_ROOT / ".pending"
SETTINGS_FILE = WEB_ROOT / "settings.json"
IMAGE_JOBS_FILE = WEB_ROOT / "image_jobs.json"
DEFAULT_PORT = int(os.environ.get("AIRP_PORT", "8765"))
OPENCODE_PORT = int(os.environ.get("OPENCODE_PORT", "4096"))

DEFAULT_SETTINGS = {
    "style": "default",
    "nsfw": "off",
    "person": "first",
    "wordCount": 600,
    "antiHijack": True,
    "backgroundNpc": True,
    "theme": "light",
    "userName": "User",
    "pageWidth": 460,
}

image_queue: queue.Queue[str] = queue.Queue()
image_lock = threading.Lock()
pending_lock = threading.Lock()
stop_event = threading.Event()


class Handler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self.json({"ok": True, "service": "opencode-airp-sillytavern", "time": now(), "opencodePort": OPENCODE_PORT, "card": get_current_card_name()})
            elif path == "/api/cards":
                self.json({"ok": True, "current": get_current_card_name(), "cards": list_cards()})
            elif path == "/api/content":
                self.json(build_content_payload())
            elif path == "/api/state":
                self.json(update_state())
            elif path == "/api/settings":
                self.json({"ok": True, **load_settings()})
            elif path == "/api/pending":
                self.json({"ok": True, "pending": PENDING_FILE.exists(), "text": read_text(INPUT_FILE)})
            elif path == "/api/openings":
                self.json({"ok": True, "openings": get_openings()})
            elif path == "/api/image-status":
                self.handle_image_status()
            elif path == "/api/image":
                self.handle_image()
            elif path == "/api/card":
                payload = get_card_payload()
                self.json({"ok": True, "card": {"id": payload["id"], "format": payload["format"], "fields": payload["fields"]}})
            elif path == "/api/worldbooks":
                self.json({"ok": True, "current": "main", "worldbooks": list_worldbooks()})
            elif path == "/api/worldbook":
                name = parse_qs(urlparse(self.path).query).get("name", ["main"])[0]
                payload = get_worldbook_payload(name)
                self.json({"ok": True, "worldbook": {"id": payload["id"], "cardId": payload["cardId"], "entries": payload["entries"]}})
            elif path == "/api/context":
                self.json({"ok": True, "context": get_context_payload()})
            else:
                super().do_GET()
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, code=500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        data = self.read_json_body()
        try:
            if path == "/api/submit":
                self.handle_submit(data)
            elif path == "/api/done":
                PENDING_FILE.unlink(missing_ok=True)
                self.json({"ok": True})
            elif path == "/api/settings":
                settings = load_settings()
                settings.update(data if isinstance(data, dict) else {})
                atomic_write_json(SETTINGS_FILE, settings)
                rebuild_context_snapshot()
                self.json({"ok": True, "settings": settings})
            elif path == "/api/play":
                self.handle_play(data)
            elif path == "/api/reroll":
                last_user = reroll_last()
                if last_user:
                    write_pending(last_user)
                self.json({"ok": True, "text": last_user})
            elif path == "/api/rollback":
                rollback(int(data.get("fromIndex", 0)))
                self.json({"ok": True})
            elif path == "/api/switch-opening":
                selected = switch_opening(int(data.get("id", 0)))
                build_content_js()
                rebuild_context_snapshot()
                self.json({"ok": True, "opening": selected})
            elif path == "/api/image-gen":
                self.handle_image_gen(data)
            elif path == "/api/card":
                card_id = data.get("id") or get_current_card_name()
                fields = data.get("fields") or {}
                payload = save_card_fields(card_id, fields)
                rebuild_context_snapshot()
                self.json({"ok": True, "card": {"id": payload["id"], "format": payload["format"], "fields": payload["fields"]}})
            elif path == "/api/worldbook":
                payload = save_worldbook_entries(data.get("name", "main"), data.get("entries") or [])
                rebuild_context_snapshot()
                self.json({"ok": True, "worldbook": {"id": payload["id"], "cardId": payload["cardId"], "entries": payload["entries"]}})
            elif path == "/api/worldbook/preview":
                self.json({"ok": True, "preview": preview_worldbook_activation(data.get("text", ""), data.get("name", "main"))})
            else:
                self.json({"ok": False, "error": "not found"}, code=404)
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, code=500)

    def handle_submit(self, data: dict) -> None:
        text = str(data.get("text", "")).strip()
        if not text:
            self.json({"ok": False, "error": "empty text"}, code=400)
            return
        context = build_turn_context(text)
        write_pending(text)
        self.json({"ok": True, "context": {"activatedLore": context.get("activatedLore", []), "metadata": context.get("metadata", {})}})

    def handle_play(self, data: dict) -> None:
        card = str(data.get("card") or data.get("name") or "").strip()
        if not card:
            self.json({"ok": False, "error": "missing card"}, code=400)
            return
        set_current_card_name(card)
        build_content_js(card)
        rebuild_context_snapshot()
        payload = get_card_payload(card)
        self.json({"ok": True, "current": card, "card": {"id": payload["id"], "fields": payload["fields"]}, "cards": list_cards()})

    def handle_image_gen(self, data: dict) -> None:
        tags = str(data.get("tags", "")).strip()
        key = str(data.get("key", "")).strip()
        if not tags:
            self.json({"ok": False, "error": "missing tags"}, code=400)
            return
        job_id = create_image_job(key, tags)
        image_queue.put(job_id)
        self.json({"ok": True, "jobId": job_id, "status": "queued"})

    def handle_image_status(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        jobs = load_image_jobs()
        job_id = params.get("id", [""])[0]
        if job_id:
            job = jobs.get(job_id)
            self.json({"ok": bool(job), "job": job, **({} if job else {"error": "job not found"})}, code=200 if job else 404)
        else:
            self.json({"ok": True, "jobs": jobs})

    def handle_image(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        raw = params.get("path", [""])[0]
        if not raw:
            self.send_error(400)
            return
        path = safe_project_path(raw)
        if not path or not path.exists() or not path.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"text": raw}

    def json(self, data: dict, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def init_runtime() -> None:
    WEB_ROOT.mkdir(exist_ok=True)
    CARDS_DIR.mkdir(exist_ok=True)
    if not SETTINGS_FILE.exists():
        atomic_write_json(SETTINGS_FILE, DEFAULT_SETTINGS)
    if not IMAGE_JOBS_FILE.exists():
        atomic_write_json(IMAGE_JOBS_FILE, {})
    PENDING_FILE.unlink(missing_ok=True)
    reset_running_image_jobs()
    current = get_current_card_name()
    if current:
        build_content_js(current)
        update_state(current)
    rebuild_context_snapshot()


def response_poller() -> None:
    from opencode_client import send_message

    while not stop_event.is_set():
        try:
            if PENDING_FILE.exists():
                with pending_lock:
                    if not PENDING_FILE.exists():
                        continue
                    user_text = read_text(INPUT_FILE).strip()
                    PENDING_FILE.unlink(missing_ok=True)
                if not user_text:
                    continue
                try:
                    reply = send_message(user_text, PROJECT_ROOT)
                except Exception as exc:
                    reply = f"OpenCode 未返回回复：{exc}"
                append_message("user", user_text)
                append_message("assistant", reply)
                finalize_turn_context(reply)
            time.sleep(1)
        except Exception as exc:
            print(f"[poller] {exc}", flush=True)
            time.sleep(2)


def image_worker() -> None:
    while not stop_event.is_set():
        try:
            job_id = image_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            run_image_job(job_id)
        finally:
            image_queue.task_done()


def create_image_job(key: str, tags: str) -> str:
    job_id = uuid4().hex
    with image_lock:
        jobs = load_image_jobs()
        jobs[job_id] = {
            "id": job_id,
            "key": key,
            "tags": tags,
            "card": get_current_card_name(),
            "status": "queued",
            "path": "",
            "error": "",
            "createdAt": now(),
            "startedAt": "",
            "finishedAt": "",
        }
        save_image_jobs(jobs)
    return job_id


def run_image_job(job_id: str) -> None:
    job = update_image_job(job_id, status="running", startedAt=now(), error="")
    if not job:
        return
    if not novelai_key_configured():
        update_image_job(job_id, status="error", error="NOVELAI_API_KEY is not configured", finishedAt=now())
        return
    card = job.get("card") or get_current_card_name()
    out_dir = get_card_dir(card) / "generated"
    out_dir.mkdir(exist_ok=True)
    script = PROJECT_ROOT / "scripts" / "novelai-generate.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "-p", job.get("tags", ""), "-s", "832x1216", "-o", str(out_dir)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        image = newest_png(out_dir)
        if result.returncode != 0 and not image:
            update_image_job(job_id, status="error", error=(result.stderr or result.stdout or "generation failed")[:500], finishedAt=now())
            return
        if not image:
            update_image_job(job_id, status="error", error="no image generated", finishedAt=now())
            return
        rel = image.relative_to(PROJECT_ROOT).as_posix()
        persist_generated_image(card, job.get("key", ""), rel)
        update_image_job(job_id, status="done", path=quote(rel), rawPath=rel, finishedAt=now())
    except subprocess.TimeoutExpired:
        update_image_job(job_id, status="error", error="NovelAI generation timeout", finishedAt=now())


def persist_generated_image(card: str, key: str, rel_path: str) -> None:
    if not key:
        return
    path = get_generated_map_path(card)
    data = safe_read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data[key] = quote(rel_path)
    atomic_write_json(path, data)
    build_content_js(card)


def load_image_jobs() -> dict:
    data = safe_read_json(IMAGE_JOBS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_image_jobs(jobs: dict) -> None:
    atomic_write_json(IMAGE_JOBS_FILE, jobs)


def update_image_job(job_id: str, **changes) -> dict | None:
    with image_lock:
        jobs = load_image_jobs()
        if job_id not in jobs:
            return None
        jobs[job_id].update(changes)
        save_image_jobs(jobs)
        return jobs[job_id]


def reset_running_image_jobs() -> None:
    jobs = load_image_jobs()
    changed = False
    for job in jobs.values():
        if job.get("status") in {"queued", "running"}:
            job.update({"status": "error", "error": "server restarted", "finishedAt": now()})
            changed = True
    if changed:
        save_image_jobs(jobs)


def load_settings() -> dict:
    current = dict(DEFAULT_SETTINGS)
    data = safe_read_json(SETTINGS_FILE, {})
    if isinstance(data, dict):
        current.update(data)
    return current


def write_pending(text: str) -> None:
    with pending_lock:
        INPUT_FILE.write_text(text, encoding="utf-8")
        PENDING_FILE.touch()


def safe_project_path(raw: str) -> Path | None:
    raw = raw.replace("\\", "/")
    candidate = (PROJECT_ROOT / raw).resolve()
    root = PROJECT_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def novelai_key_configured() -> bool:
    if os.environ.get("NOVELAI_API_KEY"):
        return True
    env = PROJECT_ROOT / ".env"
    if not env.exists():
        return False
    return bool(re.search(r"^\s*NOVELAI_API_KEY\s*=\s*.+", env.read_text(encoding="utf-8", errors="replace"), re.MULTILINE))


def newest_png(path: Path) -> Path | None:
    files = sorted(path.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def find_port(start: int) -> int:
    import socket

    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError(f"no free port found from {start}")


def main() -> None:
    os.chdir(WEB_ROOT)
    init_runtime()
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    threading.Thread(target=response_poller, daemon=True).start()
    threading.Thread(target=image_worker, daemon=True).start()
    port = find_port(DEFAULT_PORT)
    PORT_FILE.write_text(str(port), encoding="utf-8")
    print(f"OpenCode AIRP Web: http://127.0.0.1:{port}/index.html", flush=True)
    print(f"OpenCode TUI API expected at http://127.0.0.1:{OPENCODE_PORT}", flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
