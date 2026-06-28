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
    CURRENT_CARD_FILE,
    PROJECT_ROOT,
    add_relation,
    atomic_write_json,
    ensure_worldbook_relations,
    ensure_card_runtime,
    get_assets_path,
    get_card_dir,
    get_card_payload,
    get_chat_log_path,
    get_current_card_name,
    get_events_path,
    get_generated_map_path,
    get_goals_path,
    get_openings,
    get_worldbook_payload,
    list_available_card_ids,
    list_cards,
    list_worldbooks,
    load_assets,
    load_events,
    load_goals,
    load_relations,
    load_relation_suggestions,
    mtime_iso,
    preview_worldbook_activation,
    remove_relation,
    safe_read_json,
    save_assets,
    save_card_fields,
    save_events,
    save_goals,
    save_worldbook_entries,
    set_current_card_name,
    switch_opening,
    update_relation,
)
from handler import append_message, build_content_js, build_content_payload, reroll_last, rollback, update_state
from preset_config import PresetConfigManager


WEB_ROOT = Path(__file__).resolve().parent
PID_FILE = WEB_ROOT / "server.pid"
PORT_FILE = WEB_ROOT / "server-port.txt"
INPUT_FILE = WEB_ROOT / "web-input.txt"
PENDING_FILE = WEB_ROOT / ".pending"
SETTINGS_FILE = WEB_ROOT / "settings.json"
IMAGE_JOBS_FILE = WEB_ROOT / "image_jobs.json"
USER_AVATAR_FILE = WEB_ROOT / "user_avatar.png"
PRESET_CONFIG_FILE = WEB_ROOT / "preset-config.json"
PRESETS_DIR = WEB_ROOT.parent / "presets"
DEFAULT_PORT = int(os.environ.get("AIRP_PORT", "8765"))
OPENCODE_PORT = int(os.environ.get("OPENCODE_PORT", "4096"))

DEFAULT_SETTINGS = {
    "style": "default",
    "nsfw": "off",
    "person": "first",
    "wordCount": 600,
    "antiHijack": True,
    "backgroundNpc": True,
    "theme": "dark",
    "userName": "User",
    "userBio": "",
    "pageWidth": 1200,
}

image_queue: queue.Queue[str] = queue.Queue()
image_lock = threading.Lock()
pending_lock = threading.Lock()
stop_event = threading.Event()
preset_config_manager = PresetConfigManager(PRESET_CONFIG_FILE)


class Handler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        with open("D:/codebaby/Opencode--AIRP-SillyTavern/web-frontend/server_debug.log", "a", encoding="utf-8") as f:
            f.write(f"GET {path}\n")
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
            elif path == "/api/session-state":
                self.json({"ok": True, "state": read_session_state()})
            elif path == "/api/goals":
                self.json({"ok": True, "goals": load_goals()})
            elif path == "/api/events":
                self.json({"ok": True, "events": load_events()})
            elif path == "/api/assets":
                assets, capacity = load_assets()
                self.json({"ok": True, "assets": assets, "totalCapacity": capacity})
            elif path == "/api/character-image":
                self.handle_character_image()
            elif path == "/api/resources/cards":
                self.handle_resources_cards()
            elif path == "/api/cards/import":
                self.handle_cards_import()
            elif path == "/api/cards/delete":
                self.handle_cards_delete()
            elif path == "/api/relations":
                card_id = parse_qs(urlparse(self.path).query).get("cardId", [None])[0]
                relations = load_relations(card_id)
                self.json({"ok": True, "relations": relations})
            elif path == "/api/relations/suggestions":
                card_id = parse_qs(urlparse(self.path).query).get("cardId", [None])[0]
                suggestions = load_relation_suggestions(card_id)
                self.json({"ok": True, "suggestions": suggestions})
            elif path == "/api/relations/update":
                self.handle_relation_update(data)
            elif path == "/api/relations/remove":
                self.handle_relation_remove(data)
            elif path == "/api/relations/add":
                self.handle_relation_add(data)
            elif path == "/api/user-profile":
                self.json({"ok": True, **self.load_user_profile()})
            elif path == "/api/user-avatar":
                self.handle_user_avatar()
            elif path == "/api/presets":
                self.handle_presets()
            elif path == "/api/presets/scan":
                self.handle_presets_scan()
            elif path.startswith("/api/presets"):
                self.json({"ok": False, "error": "not found"}, code=404)
            else:
                super().do_GET()
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, code=500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/character-image":
                self.handle_character_image_upload()
                return
            if path == "/api/cards/import":
                self.handle_cards_import()
                return
            data = self.read_json_body()
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, code=400)
            return
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
            elif path == "/api/relations/add":
                self.handle_relation_add(data)
            elif path == "/api/relations/update":
                self.handle_relation_update(data)
            elif path == "/api/relations/remove":
                self.handle_relation_remove(data)
            elif path == "/api/goals":
                save_goals(data.get("goals") or [], data.get("cardId") or get_current_card_name())
                self.json({"ok": True, "goals": load_goals(data.get("cardId") or get_current_card_name())})
            elif path == "/api/events":
                save_events(data.get("events") or [], data.get("cardId") or get_current_card_name())
                self.json({"ok": True, "events": load_events(data.get("cardId") or get_current_card_name())})
            elif path == "/api/assets":
                card_id = data.get("cardId") or get_current_card_name()
                save_assets(data.get("assets") or [], card_id, int(data.get("totalCapacity", 50) or 50))
                assets, capacity = load_assets(card_id)
                self.json({"ok": True, "assets": assets, "totalCapacity": capacity})
            elif path == "/api/cards/delete":
                self.handle_cards_delete()
            elif path == "/api/user-profile":
                self.handle_user_profile(data)
            elif path == "/api/user-avatar":
                self.handle_user_avatar_upload(data)
            elif path == "/api/rollback":
                self.handle_rollback(data)
            elif path == "/api/message/edit":
                self.handle_message_edit(data)
            elif path == "/api/message/delete":
                self.handle_message_delete(data)
            elif path == "/api/message/backup":
                self.handle_message_backup(data)
            elif path == "/api/presets/toggle":
                self.handle_presets_toggle(data)
            elif path == "/api/presets/reorder":
                self.handle_presets_reorder(data)
            elif path == "/api/presets/select":
                self.handle_presets_select(data)
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

    def handle_presets(self) -> None:
        from preset_scanner import PresetScanner
        import os
        debug_path = os.path.join(os.path.dirname(__file__), "handle_presets_debug.log")
        with open(debug_path, "a", encoding="utf-8") as f:
            f.write(f"handle_presets called\n")
            f.write(f"PRESETS_DIR={PRESETS_DIR}, exists={PRESETS_DIR.exists()}\n")
        cfg = preset_config_manager.load()
        with open(debug_path, "a", encoding="utf-8") as f:
            f.write(f"loaded cfg with {len(cfg.presets)} presets\n")
        # Merge scanner results so the response includes actual preset entries
        if PRESETS_DIR.is_dir():
            try:
                scanner = PresetScanner(PRESETS_DIR)
                groups = scanner.scan_all()
                with open(debug_path, "a", encoding="utf-8") as f:
                    f.write(f"scanned {len(groups)} groups\n")
                preset_config_manager._merge_scanner_results(cfg, scanner)
                preset_config_manager.save(cfg)
                with open(debug_path, "a", encoding="utf-8") as f:
                    f.write(f"saved cfg, now {len(cfg.presets)} presets\n")
            except Exception as e:
                with open(debug_path, "a", encoding="utf-8") as f:
                    f.write(f"error: {e}\n")
        
        # Only return full details for the active preset to reduce payload size
        active_id = cfg.active_preset_id
        presets_summary: dict[str, Any] = {}
        for pid, pdata in cfg.presets.items():
            if pid == active_id:
                presets_summary[pid] = pdata  # full details including entries
            else:
                presets_summary[pid] = {
                    "source": pdata.get("source", ""),
                    "enabled": pdata.get("enabled", False),
                }
        
        with open(debug_path, "a", encoding="utf-8") as f:
            f.write(f"responding with active={active_id}, total={len(presets_summary)} presets\n")
        self.json({
            "ok": True,
            "activePresetId": active_id,
            "presets": presets_summary,
        })

    def handle_presets_scan(self) -> None:
        from preset_scanner import PresetScanner
        from pathlib import Path
        presets_root = PRESETS_DIR
        if not presets_root.is_dir():
            self.json({"ok": True, "presets": []})
            return
        scanner = PresetScanner(presets_root)
        groups = scanner.scan_all()
        result = []
        for group in groups:
            entries = []
            for entry in group.entries:
                entries.append({
                    "id": entry.id,
                    "name": entry.name,
                    "role": entry.role,
                    "content": entry.content,
                    "injection_position": entry.injection_position,
                    "injection_depth": entry.injection_depth,
                    "injection_order": entry.injection_order,
                    "marker": entry.marker,
                    "forbid_overrides": entry.forbid_overrides,
                })
            result.append({
                "name": group.name,
                "source": group.source.as_posix(),
                "params": group.params,
                "entries": entries,
            })
        self.json({"ok": True, "presets": result})

    def handle_presets_toggle(self, data: dict) -> None:
        preset_id = str(data.get("presetId", "")).strip()
        entry_id = str(data.get("entryId", "")).strip()
        enabled = bool(data.get("enabled", False))
        if not preset_id:
            self.json({"ok": False, "error": "presetId required"}, code=400)
            return
        if not entry_id:
            self.json({"ok": False, "error": "entryId required"}, code=400)
            return
        entry = preset_config_manager.toggle_entry(preset_id, entry_id, enabled)
        self.json({"ok": True, "entry": entry})

    def handle_presets_reorder(self, data: dict) -> None:
        preset_id = str(data.get("presetId", "")).strip()
        order = data.get("order", [])
        if not preset_id:
            self.json({"ok": False, "error": "presetId required"}, code=400)
            return
        if not isinstance(order, list):
            self.json({"ok": False, "error": "order must be a list"}, code=400)
            return
        entries = preset_config_manager.reorder_entries(preset_id, order)
        self.json({"ok": True, "entries": entries})

    def handle_presets_select(self, data: dict) -> None:
        preset_id = str(data.get("presetId", "")).strip()
        if not preset_id:
            self.json({"ok": False, "error": "presetId required"}, code=400)
            return
        preset_config_manager.select_preset(preset_id)
        cfg = preset_config_manager.load()
        self.json({"ok": True, "activePresetId": cfg.active_preset_id})

    def handle_play(self, data: dict) -> None:
        card = str(data.get("card") or data.get("name") or "").strip()
        if not card:
            self.json({"ok": False, "error": "missing card"}, code=400)
            return
        set_current_card_name(card)
        ensure_worldbook_relations(card)
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
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def handle_character_image(self) -> None:
        card_dir = get_card_dir()
        preferred = card_dir / "avatar.png"
        if preferred.exists() and preferred.is_file():
            image_path = preferred
        else:
            image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.webp']
            image_path = None
            for ext in image_extensions:
                images = list(card_dir.glob(ext))
                if images:
                    image_path = images[0]
                    break
            if not image_path:
                self.json({"ok": False, "error": "no character image found"}, code=404)
                return
        mime = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        data = image_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def handle_character_image_upload(self) -> None:
        try:
            print("[avatar-upload] upload start")
            filename, data = self.read_multipart_file("file")
            print(f"[avatar-upload] filename={filename!r}, bytes={len(data)}")
        except Exception as exc:
            print(f"[avatar-upload] parse failed: {exc}")
            self.json({"ok": False, "error": f"upload parse failed: {exc}"}, code=400)
            return
        if not data:
            print("[avatar-upload] empty file")
            self.json({"ok": False, "error": "empty file"}, code=400)
            return
        card_dir = get_card_dir()
        card_dir.mkdir(parents=True, exist_ok=True)
        target = card_dir / "avatar.png"
        try:
            target.write_bytes(data)
            print(f"[avatar-upload] saved to {target}")
        except Exception as exc:
            print(f"[avatar-upload] save failed: {exc}")
            self.json({"ok": False, "error": f"save failed: {exc}"}, code=500)
            return
        self.json({"ok": True, "path": str(target)})

    def handle_relation_add(self, data: dict) -> None:
        name = str(data.get("name", "")).strip()
        relation = str(data.get("relation", "")).strip()
        favor = int(data.get("favor", 0) or 0)
        if not name:
            self.json({"ok": False, "error": "name required"}, code=400)
            return
        card_id = data.get("cardId") or get_current_card_name()
        item = add_relation({
            "name": name,
            "relation": relation or "新角色",
            "favor": favor,
            "avatar": name[0] if name else "?",
            "source": "manual",
        }, card_id)
        self.json({"ok": True, "relation": item})

    def handle_relation_update(self, data: dict) -> None:
        relation_id = str(data.get("id", "")).strip()
        if not relation_id:
            self.json({"ok": False, "error": "id required"}, code=400)
            return
        card_id = data.get("cardId") or get_current_card_name()
        updates = {k: v for k, v in data.items() if k not in {"id", "cardId"}}
        updated = update_relation(relation_id, updates, card_id)
        if not updated:
            self.json({"ok": False, "error": "relation not found"}, code=404)
            return
        self.json({"ok": True, "relation": updated})

    def handle_relation_remove(self, data: dict) -> None:
        relation_id = str(data.get("id", "")).strip()
        if not relation_id:
            self.json({"ok": False, "error": "id required"}, code=400)
            return
        card_id = data.get("cardId") or get_current_card_name()
        ok = remove_relation(relation_id, card_id)
        if not ok:
            self.json({"ok": False, "error": "relation not found"}, code=404)
            return
        self.json({"ok": True})

    def handle_rollback(self, data: dict) -> None:
        from handler import rollback
        from_index = int(data.get("fromIndex", 0) or 0)
        rollback(from_index)
        self.json({"ok": True, "fromIndex": from_index})

    def handle_message_edit(self, data: dict) -> None:
        message_id = str(data.get("id", "")).strip()
        new_content = str(data.get("content", "")).strip()
        if not message_id:
            self.json({"ok": False, "error": "id required"}, code=400)
            return
        from handler import edit_message
        ok = edit_message(message_id, new_content)
        if not ok:
            self.json({"ok": False, "error": "message not found"}, code=404)
            return
        self.json({"ok": True})

    def handle_message_delete(self, data: dict) -> None:
        message_id = str(data.get("id", "")).strip()
        if not message_id:
            self.json({"ok": False, "error": "id required"}, code=400)
            return
        from handler import delete_message
        ok = delete_message(message_id)
        if not ok:
            self.json({"ok": False, "error": "message not found"}, code=404)
            return
        self.json({"ok": True})

    def handle_message_backup(self, data: dict) -> None:
        from handler import backup_messages
        messages = data.get("messages")
        if messages:
            backup_messages(messages)
        else:
            backup_messages()
        self.json({"ok": True})

    def load_user_profile(self) -> dict:
        settings = load_settings()
        return {
            "userName": settings.get("userName", "User"),
            "userBio": settings.get("userBio", ""),
            "hasAvatar": USER_AVATAR_FILE.exists(),
        }

    def handle_user_profile(self, data: dict) -> None:
        settings = load_settings()
        if "userName" in data:
            settings["userName"] = str(data["userName"]).strip()
        if "userBio" in data:
            settings["userBio"] = str(data["userBio"]).strip()
        atomic_write_json(SETTINGS_FILE, settings)
        rebuild_context_snapshot()
        self.json({
            "ok": True,
            "userName": settings.get("userName", ""),
            "userBio": settings.get("userBio", ""),
        })

    def handle_user_avatar(self) -> None:
        if USER_AVATAR_FILE.exists():
            mime = mimetypes.guess_type(str(USER_AVATAR_FILE))[0] or "application/octet-stream"
            data = USER_AVATAR_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.json({"ok": False, "error": "no avatar"}, code=404)

    def handle_user_avatar_upload(self, data: dict) -> None:
        import base64
        base64_data = str(data.get("base64", "")).strip()
        if not base64_data:
            self.json({"ok": False, "error": "no data"}, code=400)
            return
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        try:
            binary = base64.b64decode(base64_data)
            USER_AVATAR_FILE.write_bytes(binary)
            self.json({"ok": True})
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, code=500)

    def handle_resources_cards(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        card_id = params.get("cardId", [None])[0]
        cards = []
        for cid in list_available_card_ids():
            try:
                ensure_card_runtime(cid)
                payload = get_card_payload(cid)
                chat = safe_read_json(get_chat_log_path(cid), [])
                card_dir = get_card_dir(cid)
                image_path = None
                for ext in ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"]:
                    images = list(card_dir.glob(ext))
                    if images:
                        image_path = images[0]
                        break
                cards.append({
                    "id": cid,
                    "name": payload["fields"].get("name") or cid,
                    "format": payload["format"],
                    "description": payload["fields"].get("description", ""),
                    "personality": payload["fields"].get("personality", ""),
                    "messages": len(chat) if isinstance(chat, list) else 0,
                    "hasImage": image_path is not None,
                    "imagePath": image_path.relative_to(PROJECT_ROOT).as_posix() if image_path else None,
                    "updatedAt": mtime_iso(card_dir / "card.json"),
                })
            except Exception as exc:
                cards.append({"id": cid, "name": cid, "error": str(exc)})
        active = get_current_card_name()
        self.json({"ok": True, "current": active, "cards": cards})

    def handle_cards_import(self) -> None:
        try:
            files = self.read_multipart_files("file")
        except Exception as exc:
            self.json({"ok": False, "error": f"upload parse failed: {exc}"}, code=400)
            return
        if not files:
            self.json({"ok": False, "error": "no files uploaded"}, code=400)
            return
        imported = []
        for filename, data in files:
            if not data:
                continue
            if not filename.lower().endswith(".png"):
                continue
            safe_name = re.sub(r'[\\/:*?"<>|]', "_", filename)
            base_name = Path(safe_name).stem.strip() or "未命名角色卡"
            card_dir = CARDS_DIR / base_name
            if card_dir.exists():
                card_dir = CARDS_DIR / f"{base_name}_{int(datetime.now().timestamp())}"
            card_dir.mkdir(parents=True, exist_ok=True)
            target = card_dir / safe_name
            try:
                target.write_bytes(data)
                result = ensure_card_runtime(card_dir.name)
                imported.append({
                    "id": card_dir.name,
                    "name": result.get("cardName") or card_dir.name,
                    "source": filename,
                    "worldbookEntries": result.get("worldbookEntries", 0),
                    "openings": result.get("openings", 0),
                })
            except Exception as exc:
                imported.append({"id": card_dir.name, "name": card_dir.name, "error": str(exc)})
        if not imported:
            self.json({"ok": False, "error": "no valid png files imported"}, code=400)
            return
        self.json({"ok": True, "imported": imported, "cards": list_cards()})

    def handle_cards_delete(self) -> None:
        data = self.read_json_body()
        card_id = str(data.get("id", "")).strip()
        if not card_id:
            self.json({"ok": False, "error": "id required"}, code=400)
            return
        card_dir = get_card_dir(card_id)
        if not card_dir.exists():
            self.json({"ok": False, "error": "card not found"}, code=404)
            return
        current = get_current_card_name()
        import shutil
        try:
            shutil.rmtree(card_dir)
        except Exception as exc:
            self.json({"ok": False, "error": str(exc)}, code=500)
            return
        next_card = None
        if current == card_id:
            available = list_available_card_ids()
            next_card = available[0] if available else None
            if next_card:
                set_current_card_name(next_card)
                build_content_js(next_card)
                rebuild_context_snapshot()
            else:
                CURRENT_CARD_FILE.unlink(missing_ok=True)
        self.json({"ok": True, "deleted": card_id, "current": next_card, "cards": list_cards()})

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"text": raw}

    def read_multipart_file(self, field_name: str = "file"):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("not multipart")
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part.split("=", 1)[1].strip('"')
                break
        if not boundary:
            raise ValueError("no boundary")
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        boundary_bytes = ("--" + boundary).encode("utf-8")
        parts = raw.split(b"--" + boundary.encode("utf-8"))
        for part in parts:
            headers_body = part.split(b"\r\n\r\n", 1)
            if len(headers_body) != 2:
                continue
            header_lines = headers_body[0].decode("utf-8", errors="replace").split("\r\n")
            disposition = None
            for line in header_lines:
                if line.lower().startswith("content-disposition:"):
                    disposition = line
                    break
            if not disposition:
                continue
            if field_name not in disposition:
                continue
            body = headers_body[1]
            if body.endswith(b"\r\n"):
                body = body[:-2]
            filename = None
            match = re.search(r'filename="([^"]+)"', disposition)
            if match:
                filename = match.group(1)
            if not filename:
                filename = field_name + ".bin"
            return filename, body
        raise ValueError("file not found")

    def read_multipart_files(self, field_name: str = "file"):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("not a multipart request")
        boundary = None
        match = re.search(r"boundary=([^;]+)", content_type)
        if not match:
            raise ValueError("missing boundary")
        boundary = match.group(1).strip()
        if boundary.startswith('"') and boundary.endswith('"'):
            boundary = boundary[1:-1]
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return []
        raw = self.rfile.read(length)
        boundary_bytes = boundary.encode("utf-8")
        parts = raw.split(b"--" + boundary_bytes)
        results = []
        for part in parts:
            headers_body = part.split(b"\r\n\r\n", 1)
            if len(headers_body) != 2:
                continue
            header_lines = headers_body[0].decode("utf-8", errors="replace").split("\r\n")
            disposition = None
            for line in header_lines:
                if line.lower().startswith("content-disposition:"):
                    disposition = line
                    break
            if not disposition:
                continue
            if field_name not in disposition:
                continue
            body = headers_body[1]
            if body.endswith(b"\r\n"):
                body = body[:-2]
            filename = None
            match = re.search(r'filename="([^"]+)"', disposition)
            if match:
                filename = match.group(1)
            if not filename:
                filename = field_name + ".bin"
            results.append((filename, body))
        return results

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
    backend = get_image_backend()
    if backend == "agnes":
        if not image_backend_configured("agnes"):
            update_image_job(job_id, status="error", error="AGNES_API_KEY is not configured", finishedAt=now())
            return
    else:
        if not image_backend_configured("novelai"):
            update_image_job(job_id, status="error", error="NOVELAI_API_KEY is not configured", finishedAt=now())
            return
    card = job.get("card") or get_current_card_name()
    out_dir = get_card_dir(card) / "generated"
    out_dir.mkdir(exist_ok=True)

    if backend == "agnes":
        script = PROJECT_ROOT / "scripts" / "agnes-generate.py"
        cmd = [
            sys.executable, str(script),
            "-p", job.get("tags", ""),
            "-s", "1024x768",
            "-o", str(out_dir),
        ]
    else:
        script = PROJECT_ROOT / "scripts" / "novelai-generate.py"
        cmd = [
            sys.executable, str(script),
            "-p", job.get("tags", ""),
            "-s", "832x1216",
            "-o", str(out_dir),
        ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        image = None
        if backend == "agnes":
            m = re.search(r"\[Agnes\] 保存:\s*(.+)", result.stdout)
            if m:
                p = Path(m.group(1).strip())
                if p.exists() and p.is_file():
                    image = p
        else:
            m = re.search(r"\[NAI\] 保存:\s*(.+)", result.stdout)
            if m:
                p = Path(m.group(1).strip())
                if p.exists() and p.is_file():
                    image = p
        if not image:
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
        update_image_job(job_id, status="error", error=f"{backend.capitalize()} generation timeout", finishedAt=now())


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


def _has_env_key(name: str) -> bool:
    if os.environ.get(name):
        return True
    env = PROJECT_ROOT / ".env"
    if not env.exists():
        return False
    return bool(re.search(rf"^\s*{name}\s*=\s*.+", env.read_text(encoding="utf-8", errors="replace"), re.MULTILINE))


def image_backend_configured(backend: str) -> bool:
    if backend == "agnes":
        return _has_env_key("AGNES_API_KEY")
    return _has_env_key("NOVELAI_API_KEY")


def get_image_backend() -> str:
    if image_backend_configured("agnes"):
        return "agnes"
    return "novelai"


def novelai_key_configured() -> bool:
    return image_backend_configured("novelai")


def newest_png(path: Path) -> Path | None:
    files = sorted(path.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_session_state(card_id: str | None = None) -> dict:
    path = get_card_dir(card_id) / "session-state.md"
    text = read_text(path)
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- "):
            content = line[2:]
            if ": " in content:
                key, value = content.split(": ", 1)
                result[key.strip()] = value.strip()
    return result


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
