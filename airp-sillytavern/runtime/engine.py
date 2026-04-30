"""
Main engine — orchestrates the AIRP runtime.

CLI usage:
    python -m runtime.engine intake file1.json file2.json ...
    python -m runtime.engine turn "user message" [--session session/]
    python -m runtime.engine post "assistant response" [--session session/]
    python -m runtime.engine command <swipe|regen|continue|impersonate|inspect|lore|memory> [args]
    python -m runtime.engine status [--session session/]

All output is JSON to stdout for easy consumption by the agent.
"""

from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path
from typing import Any

from .loader import intake, classify, normalize_preset, normalize_character, normalize_worldbook, normalize_persona
from .state import SessionState, ChatHistory
from .worldinfo import activate
from .context_builder import build
from .commands import (
    SwipeManager, cmd_swipe, cmd_regen, cmd_continue,
    cmd_impersonate, cmd_inspect, cmd_lore, cmd_memory,
)
from .tokenizer import using_tiktoken


# ---------------------------------------------------------------------------
# Default configs
# ---------------------------------------------------------------------------

DEFAULT_PRESET = {
    "main_prompt": (
        "Write {{char}}'s next reply in a fictional chat between "
        "{{char}} and {{user}}. Write 1 reply only in internet RP style, "
        "italicize actions, and avoid quotation marks. Be proactive, "
        "creative, and drive the plot and conversation forward."
    ),
    "auxiliary_prompt": "",
    "post_history_instructions": "",
    "context_limit": 8192,
    "max_tokens": 300,
    "temperature": 1.0,
    "top_p": 1.0,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "scan_depth": 2,
    "wi_budget": 512,
    "stream": True,
    "raw": {},
}

DEFAULT_PERSONA = {
    "name": "User",
    "description": "",
    "position": "prompt_manager",
}


# ---------------------------------------------------------------------------
# Engine operations
# ---------------------------------------------------------------------------

def do_intake(sources: list[str], session_dir: str = "session") -> dict:
    """Parse and classify artifacts, save to session directory."""
    sdir = Path(session_dir)
    sdir.mkdir(parents=True, exist_ok=True)

    result = intake([Path(s) if Path(s).exists() else s for s in sources])

    # Apply defaults for missing artifacts
    if not result["preset"]:
        result["preset"] = DEFAULT_PRESET

    if not result["persona"]:
        char_name = ""
        if result["character"]:
            char_name = result["character"].get("data", {}).get("name", "")
        result["persona"] = {**DEFAULT_PERSONA}

    if not result["worldbook"]:
        result["worldbook"] = {"entries": []}

    # Save to session
    for key in ("preset", "character", "persona", "worldbook"):
        if result[key]:
            (sdir / f"{key}.json").write_text(
                json.dumps(result[key], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # Initialize state
    char_name = ""
    user_name = result["persona"]["name"]
    if result["character"]:
        char_name = result["character"].get("data", {}).get("name", "")

    state = SessionState(sdir)
    state.init(char_name=char_name, user_name=user_name)

    # Initialize empty history
    history = ChatHistory(sdir)

    # Prepare opening message
    opening = ""
    if result["character"]:
        char_data = result["character"].get("data", {})
        opening = char_data.get("first_mes", "")
        alternates = char_data.get("alternate_greetings", [])
    else:
        alternates = []

    # Build summary
    summary = {
        "status": "ok",
        "session_dir": str(sdir),
        "tokenizer": "tiktoken" if using_tiktoken() else "heuristic",
        "artifacts": {
            "preset": bool(result["preset"]),
            "character": bool(result["character"]),
            "persona": bool(result["persona"]),
            "worldbook": bool(result["worldbook"]),
            "worldbook_entries": len(result["worldbook"]["entries"]) if result["worldbook"] else 0,
        },
        "char_name": char_name,
        "user_name": user_name,
        "opening": opening,
        "alternate_greetings_count": len(alternates),
        "errors": result["errors"],
        "unknown_artifacts": len(result["unknown"]),
    }

    # If there's an opening, log it as first assistant message
    if opening:
        from .macros import resolve
        resolved_opening = resolve(
            opening,
            char_name=char_name,
            user_name=user_name,
        )
        history.append("assistant", resolved_opening, turn=0, type="opening")
        summary["resolved_opening"] = resolved_opening

    return summary


def do_turn(user_message: str, session_dir: str = "session") -> dict:
    """
    Process a user turn:
    1. Load session config
    2. Scan World Info
    3. Build context
    4. Return assembled context + metadata for the model to generate from
    """
    sdir = Path(session_dir)
    state = SessionState(sdir)
    history = ChatHistory(sdir)

    # Load config
    config = _load_config(sdir)
    preset = config["preset"]
    character = config["character"]
    persona = config["persona"]
    worldbook = config["worldbook"]

    char_name = character.get("data", character).get("name", "Character")
    user_name = persona.get("name", "User")

    # Log user message
    history.append("user", user_message, turn=state.get("turn", 0))

    # Activate World Info
    activated = activate(
        entries=worldbook.get("entries", []),
        chat_history=history.all(),
        scan_depth=preset.get("scan_depth", 2),
        token_budget=preset.get("wi_budget", 512),
        char_name=char_name,
        user_name=user_name,
    )

    # Build context
    context = build(
        preset=preset,
        character=character,
        persona=persona,
        activated_lore=activated,
        chat_history=history.all()[:-1],  # exclude the just-added user msg
        user_message=user_message,
        context_limit=preset.get("context_limit", 8192),
        max_response=preset.get("max_tokens", 300),
    )

    return {
        "status": "ok",
        "turn": state.get("turn", 0),
        "system_prompt": context["system"],
        "messages": context["messages"],
        "metadata": context["metadata"],
        "activated_lore": [
            {"comment": e.get("comment", ""), "key": e.get("key", []), "reason": e.get("_activation", "")}
            for e in activated
        ],
        "state_summary": state.summary(),
    }


def do_post(assistant_response: str, session_dir: str = "session",
            state_updates: dict | None = None) -> dict:
    """
    Post-generation: log assistant response, update state, store swipe.
    """
    sdir = Path(session_dir)
    state = SessionState(sdir)
    history = ChatHistory(sdir)
    swipes = SwipeManager(sdir)

    turn = state.next_turn()
    history.append("assistant", assistant_response, turn=turn)
    swipes.store(turn, assistant_response)

    if state_updates:
        state.update(**state_updates)

    return {
        "status": "ok",
        "turn": turn,
        "history_length": history.count(),
        "swipe_index": swipes.count(turn) - 1,
    }


def do_command(command: str, args: list[str] | None = None,
               session_dir: str = "session") -> dict:
    """Execute a runtime command."""
    sdir = Path(session_dir)
    state = SessionState(sdir)
    history = ChatHistory(sdir)

    if command == "swipe":
        swipes = SwipeManager(sdir)
        return cmd_swipe(state, history, swipes)

    elif command == "regen":
        return cmd_regen(state, history)

    elif command == "continue":
        return cmd_continue(state, history)

    elif command == "impersonate":
        persona = _load_json(sdir / "persona.json") or DEFAULT_PERSONA
        return cmd_impersonate(state, persona)

    elif command == "inspect":
        # Need to rebuild context to inspect it
        config = _load_config(sdir)
        activated = activate(
            entries=config["worldbook"].get("entries", []),
            chat_history=history.all(),
            scan_depth=config["preset"].get("scan_depth", 2),
            token_budget=config["preset"].get("wi_budget", 512),
        )
        context = build(
            preset=config["preset"],
            character=config["character"],
            persona=config["persona"],
            activated_lore=activated,
            chat_history=history.all(),
            context_limit=config["preset"].get("context_limit", 8192),
            max_response=config["preset"].get("max_tokens", 300),
        )
        return cmd_inspect(context)

    elif command == "lore":
        worldbook = _load_json(sdir / "worldbook.json") or {"entries": []}
        query = args[0] if args else ""
        return cmd_lore(worldbook.get("entries", []), query)

    elif command == "memory":
        return cmd_memory(state)

    elif command == "status":
        return {
            "command": "status",
            "turn": state.get("turn", 0),
            "history_length": history.count(),
            "state": state.to_dict(),
            "tokenizer": "tiktoken" if using_tiktoken() else "heuristic",
        }

    else:
        return {"command": command, "error": f"Unknown command: {command}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _load_config(sdir: Path) -> dict:
    return {
        "preset": _load_json(sdir / "preset.json") or DEFAULT_PRESET,
        "character": _load_json(sdir / "character.json") or {},
        "persona": _load_json(sdir / "persona.json") or DEFAULT_PERSONA,
        "worldbook": _load_json(sdir / "worldbook.json") or {"entries": []},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AIRP SillyTavern Runtime Engine")
    parser.add_argument("--session", default="session", help="Session directory")
    sub = parser.add_subparsers(dest="action", required=True)

    # intake
    p_intake = sub.add_parser("intake", help="Parse and classify artifacts")
    p_intake.add_argument("files", nargs="+", help="JSON files to process")

    # turn
    p_turn = sub.add_parser("turn", help="Process a user turn")
    p_turn.add_argument("message", help="User message text")

    # post
    p_post = sub.add_parser("post", help="Post-generation update")
    p_post.add_argument("response", help="Assistant response text")
    p_post.add_argument("--state", default=None, help="JSON state updates")

    # command
    p_cmd = sub.add_parser("command", help="Execute a runtime command")
    p_cmd.add_argument("cmd", help="Command name")
    p_cmd.add_argument("args", nargs="*", help="Command arguments")

    # status
    sub.add_parser("status", help="Show session status")

    args = parser.parse_args()

    if args.action == "intake":
        result = do_intake(args.files, args.session)
    elif args.action == "turn":
        result = do_turn(args.message, args.session)
    elif args.action == "post":
        state_updates = json.loads(args.state) if args.state else None
        result = do_post(args.response, args.session, state_updates)
    elif args.action == "command":
        result = do_command(args.cmd, args.args, args.session)
    elif args.action == "status":
        result = do_command("status", session_dir=args.session)
    else:
        result = {"error": f"Unknown action: {args.action}"}

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
