"""Tests for preset API endpoints in server.py — TDD RED phase."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from server import Handler
from preset_config import PresetConfig, PresetConfigManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeHandler:
    """Create a Handler instance with mocked I/O for direct method calls."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self._setup()

    def _setup(self):
        import server as server_mod

        self.monkeypatch.chdir(self.tmp_path)
        self.monkeypatch.setattr(server_mod, "SETTINGS_FILE", self.tmp_path / "settings.json", raising=False)
        self.monkeypatch.setattr(server_mod, "INPUT_FILE", self.tmp_path / "web-input.txt", raising=False)
        self.monkeypatch.setattr(server_mod, "PENDING_FILE", self.tmp_path / ".pending", raising=False)
        self.monkeypatch.setattr(server_mod, "IMAGE_JOBS_FILE", self.tmp_path / "image_jobs.json", raising=False)
        # Use a fresh preset config file per test
        preset_config_path = self.tmp_path / "preset-config.json"
        self.monkeypatch.setattr(server_mod, "PRESET_CONFIG_FILE", preset_config_path, raising=False)
        self.monkeypatch.setattr(server_mod, "preset_config_manager", PresetConfigManager(preset_config_path), raising=False)
        # Isolate presets dir for scan tests
        presets_dir = self.tmp_path / "presets"
        presets_dir.mkdir(exist_ok=True)
        self.monkeypatch.setattr(server_mod, "PRESETS_DIR", presets_dir, raising=False)

        (self.tmp_path / "settings.json").write_text("{}", encoding="utf-8")
        (self.tmp_path / "image_jobs.json").write_text("{}", encoding="utf-8")

        # Create handler instance without going through HTTP server
        self.handler = object.__new__(Handler)
        self.handler.client_address = ("127.0.0.1", 0)
        self.handler.server = server_mod
        self.handler.path = "/"
        self.handler.command = "GET"
        self.handler.requestline = "GET / HTTP/1.1"
        self.handler.request_version = "HTTP/1.1"
        self.handler.headers = {}
        self.handler.close_connection = False
        self.handler.request_body_decoded = False

        self._response_buffer = io.BytesIO()
        self.handler.wfile = self._response_buffer
        self.handler.rfile = io.BytesIO(b"{}")

    def set_path(self, path: str, method: str = "GET"):
        self.handler.path = path
        self.handler.command = method
        self.handler.requestline = f"{method} {path} HTTP/1.1"

    def set_json_body(self, body: dict):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.handler.headers = {"Content-Length": str(len(raw))}
        self.handler.rfile = io.BytesIO(raw)

    def get_response(self) -> dict:
        raw = self._response_buffer.getvalue()
        if not raw:
            return {}
        # Strip HTTP headers to get JSON body
        try:
            body_start = raw.index(b"\r\n\r\n") + 4
            body = raw[body_start:]
        except ValueError:
            body = raw
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return {"raw": body.decode("utf-8", errors="replace")}

    def do_GET(self, path: str) -> dict:
        self._response_buffer = io.BytesIO()
        self.handler.wfile = self._response_buffer
        self.handler.rfile = io.BytesIO(b"{}")
        self.set_path(path, "GET")
        Handler.do_GET(self.handler)
        return self.get_response()

    def do_POST(self, path: str, body: dict) -> dict:
        self._response_buffer = io.BytesIO()
        self.handler.wfile = self._response_buffer
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.handler.headers = {"Content-Length": str(len(raw))}
        self.handler.rfile = io.BytesIO(raw)
        self.set_path(path, "POST")
        Handler.do_POST(self.handler)
        return self.get_response()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return _FakeHandler(tmp_path, monkeypatch)


# ---------------------------------------------------------------------------
# Tests: GET /api/presets
# ---------------------------------------------------------------------------


class TestGetPresets:
    def test_returns_empty_when_no_config(self, client: _FakeHandler):
        resp = client.do_GET("/api/presets")
        assert resp["ok"] is True
        assert resp["activePresetId"] == ""
        assert resp["presets"] == {}

    def test_returns_saved_presets(self, client: _FakeHandler, tmp_path: Path):
        manager = PresetConfigManager(tmp_path / "preset-config.json")
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {"e1": {"enabled": True, "order": 1}},
                    }
                },
            )
        )
        resp = client.do_GET("/api/presets")
        assert resp["ok"] is True
        assert resp["activePresetId"] == "p1"
        assert "p1" in resp["presets"]
        assert resp["presets"]["p1"]["entries"]["e1"]["enabled"] is True

    def test_returns_404_for_unknown_path(self, client: _FakeHandler):
        resp = client.do_GET("/api/presets/unknown")
        assert resp["ok"] is False
        assert resp["error"] == "not found"


# ---------------------------------------------------------------------------
# Tests: POST /api/presets/toggle
# ---------------------------------------------------------------------------


class TestTogglePresetEntry:
    def test_toggle_enables_entry(self, client: _FakeHandler, tmp_path: Path):
        manager = client.handler.server.preset_config_manager
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {"e1": {"enabled": False, "order": 1}},
                    }
                },
            )
        )
        resp = client.do_POST("/api/presets/toggle", {"presetId": "p1", "entryId": "e1", "enabled": True})
        assert resp["ok"] is True
        assert resp["entry"]["enabled"] is True

    def test_toggle_disables_entry(self, client: _FakeHandler, tmp_path: Path):
        manager = client.handler.server.preset_config_manager
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {"e1": {"enabled": True, "order": 1}},
                    }
                },
            )
        )
        resp = client.do_POST("/api/presets/toggle", {"presetId": "p1", "entryId": "e1", "enabled": False})
        assert resp["ok"] is True
        assert resp["entry"]["enabled"] is False

    def test_toggle_creates_missing_entry(self, client: _FakeHandler, tmp_path: Path):
        manager = client.handler.server.preset_config_manager
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {},
                    }
                },
            )
        )
        resp = client.do_POST("/api/presets/toggle", {"presetId": "p1", "entryId": "e-new", "enabled": True})
        assert resp["ok"] is True
        assert resp["entry"]["enabled"] is True

    def test_toggle_requires_preset_id(self, client: _FakeHandler):
        resp = client.do_POST("/api/presets/toggle", {"entryId": "e1", "enabled": True})
        assert resp["ok"] is False
        assert resp["error"] == "presetId required"

    def test_toggle_requires_entry_id(self, client: _FakeHandler):
        resp = client.do_POST("/api/presets/toggle", {"presetId": "p1", "enabled": True})
        assert resp["ok"] is False
        assert resp["error"] == "entryId required"


# ---------------------------------------------------------------------------
# Tests: POST /api/presets/reorder
# ---------------------------------------------------------------------------


class TestReorderPresetEntries:
    def test_reorder_changes_order(self, client: _FakeHandler, tmp_path: Path):
        manager = client.handler.server.preset_config_manager
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {
                            "a": {"enabled": True, "order": 1},
                            "b": {"enabled": True, "order": 2},
                        },
                    }
                },
            )
        )
        resp = client.do_POST("/api/presets/reorder", {"presetId": "p1", "order": ["b", "a"]})
        assert resp["ok"] is True
        assert resp["entries"]["b"]["order"] == 1
        assert resp["entries"]["a"]["order"] == 2

    def test_reorder_preserves_enabled_flags(self, client: _FakeHandler, tmp_path: Path):
        manager = client.handler.server.preset_config_manager
        manager.save(
            PresetConfig(
                active_preset_id="p1",
                presets={
                    "p1": {
                        "source": "presets/p1.json",
                        "enabled": True,
                        "entries": {
                            "a": {"enabled": False, "order": 1},
                            "b": {"enabled": True, "order": 2},
                        },
                    }
                },
            )
        )
        resp = client.do_POST("/api/presets/reorder", {"presetId": "p1", "order": ["b", "a"]})
        assert resp["ok"] is True
        assert resp["entries"]["b"]["enabled"] is True
        assert resp["entries"]["a"]["enabled"] is False

    def test_reorder_requires_preset_id(self, client: _FakeHandler):
        resp = client.do_POST("/api/presets/reorder", {"order": ["a"]})
        assert resp["ok"] is False
        assert resp["error"] == "presetId required"

    def test_reorder_requires_order_list(self, client: _FakeHandler):
        resp = client.do_POST("/api/presets/reorder", {"presetId": "p1", "order": "not-a-list"})
        assert resp["ok"] is False
        assert resp["error"] == "order must be a list"


# ---------------------------------------------------------------------------
# Tests: POST /api/presets/select
# ---------------------------------------------------------------------------


class TestSelectPreset:
    def test_select_changes_active_preset(self, client: _FakeHandler, tmp_path: Path):
        manager = client.handler.server.preset_config_manager
        manager.save(
            PresetConfig(
                active_preset_id="old",
                presets={},
            )
        )
        resp = client.do_POST("/api/presets/select", {"presetId": "new"})
        assert resp["ok"] is True
        assert resp["activePresetId"] == "new"

    def test_select_persists_to_file(self, client: _FakeHandler, tmp_path: Path):
        manager = client.handler.server.preset_config_manager
        manager.save(
            PresetConfig(
                active_preset_id="old",
                presets={},
            )
        )
        resp = client.do_POST("/api/presets/select", {"presetId": "p1"})
        assert resp["ok"] is True
        raw = json.loads((tmp_path / "preset-config.json").read_text(encoding="utf-8"))
        assert raw["activePresetId"] == "p1"

    def test_select_requires_preset_id(self, client: _FakeHandler):
        resp = client.do_POST("/api/presets/select", {})
        assert resp["ok"] is False
        assert resp["error"] == "presetId required"


# ---------------------------------------------------------------------------
# Tests: GET /api/presets/scan
# ---------------------------------------------------------------------------


class TestScanPresets:
    def test_scan_returns_presets_from_dir(self, client: _FakeHandler, tmp_path: Path):
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir(exist_ok=True)
        (presets_dir / "p1.json").write_text(
            json.dumps(
                {
                    "temperature": 1.0,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0,
                    "top_p": 1.0,
                    "top_k": 0,
                    "top_a": 0,
                    "min_p": 0,
                    "repetition_penalty": 1,
                    "openai_max_context": 4096,
                    "openai_max_tokens": 2048,
                    "wrap_in_quotes": False,
                    "names_behavior": 0,
                    "send_if_empty": "",
                    "impersonation_prompt": "",
                    "new_chat_prompt": "",
                    "new_group_chat_prompt": "",
                    "new_example_chat_prompt": "",
                    "continue_nudge_prompt": "",
                    "bias_preset_selected": "Default (none)",
                    "max_context_unlocked": True,
                    "wi_format": "{0}",
                    "scenario_format": "{{scenario}}",
                    "personality_format": "{{personality}}",
                    "group_nudge_prompt": "",
                    "stream_openai": True,
                    "prompts": [
                        {
                            "identifier": "e1",
                            "name": "Entry",
                            "enabled": True,
                            "injection_position": 0,
                            "injection_depth": 4,
                            "injection_order": 100,
                            "role": "system",
                            "content": "test",
                            "system_prompt": False,
                            "marker": False,
                            "forbid_overrides": False,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        resp = client.do_GET("/api/presets/scan")
        assert resp["ok"] is True
        assert len(resp["presets"]) == 1
        assert resp["presets"][0]["name"] == "p1"
        assert len(resp["presets"][0]["entries"]) == 1

    def test_scan_returns_empty_when_no_presets_dir(self, client: _FakeHandler):
        resp = client.do_GET("/api/presets/scan")
        assert resp["ok"] is True
        assert resp["presets"] == []
