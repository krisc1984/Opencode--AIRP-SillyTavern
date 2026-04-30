"""
Context builder — assembles prompt blocks within a token budget.

Mirrors the SillyTavern Prompt Manager order:
  main → worldInfoBefore → personaDescription → charDescription →
  charPersonality → scenario → enhanceDefinitions → auxiliaryPrompt →
  worldInfoAfter → dialogueExamples → chatHistory →
  postHistoryInstructions → (current user message)
"""

from __future__ import annotations
from typing import Any
from .tokenizer import count_tokens, count_messages
from .macros import resolve


# Default Prompt Manager block order (matches SillyTavern release default)
DEFAULT_BLOCK_ORDER = [
    "main",
    "worldInfoBefore",
    "personaDescription",
    "charDescription",
    "charPersonality",
    "scenario",
    "enhanceDefinitions",
    "auxiliaryPrompt",
    "worldInfoAfter",
    "dialogueExamples",
    "chatHistory",
    "postHistoryInstructions",
]


def build(
    preset: dict,
    character: dict,
    persona: dict,
    activated_lore: list[dict],
    chat_history: list[dict],
    user_message: str = "",
    context_limit: int = 8192,
    max_response: int = 300,
) -> dict:
    """
    Assemble the full prompt context.

    Returns a dict with:
      - system: the system-level prompt string
      - messages: the chat messages list (trimmed to fit budget)
      - metadata: token breakdown per block
    """
    char_data = character.get("data", character)
    char_name = char_data.get("name", "Character")
    user_name = persona.get("name", "User")

    macro_kwargs = dict(
        char_name=char_name,
        user_name=user_name,
        scenario=char_data.get("scenario", ""),
        personality=char_data.get("personality", ""),
    )

    budget = context_limit - max_response

    # ── Collect blocks ──────────────────────────────────────────────────
    blocks: dict[str, str] = {}

    # Main prompt
    main_prompt = preset.get("main_prompt") or char_data.get("system_prompt") or (
        "Write {{char}}'s next reply in a fictional chat between "
        "{{char}} and {{user}}. Write 1 reply only in internet RP style, "
        "italicize actions, and avoid quotation marks. Be proactive, "
        "creative, and drive the plot and conversation forward."
    )
    blocks["main"] = resolve(main_prompt, **macro_kwargs)

    # World Info — before character definitions
    wi_before = [
        e["content"] for e in activated_lore
        if e.get("position", 1) == 0  # position 0 = before char defs
    ]
    blocks["worldInfoBefore"] = resolve("\n".join(wi_before), **macro_kwargs) if wi_before else ""

    # Persona description
    blocks["personaDescription"] = resolve(
        persona.get("description", ""),
        **macro_kwargs,
    )

    # Character description
    blocks["charDescription"] = resolve(
        char_data.get("description", ""),
        **macro_kwargs,
    )

    # Character personality
    blocks["charPersonality"] = resolve(
        char_data.get("personality", ""),
        **macro_kwargs,
    )

    # Scenario
    blocks["scenario"] = resolve(
        char_data.get("scenario", ""),
        **macro_kwargs,
    )

    # Enhance definitions — usually off
    blocks["enhanceDefinitions"] = ""

    # Auxiliary prompt / NSFW prompt
    aux = preset.get("auxiliary_prompt", "")
    blocks["auxiliaryPrompt"] = resolve(aux, **macro_kwargs)

    # World Info — after character definitions
    wi_after = [
        e["content"] for e in activated_lore
        if e.get("position", 1) == 1  # position 1 = after char defs
    ]
    blocks["worldInfoAfter"] = resolve("\n".join(wi_after), **macro_kwargs) if wi_after else ""

    # Dialogue examples
    blocks["dialogueExamples"] = resolve(
        char_data.get("mes_example", ""),
        **macro_kwargs,
    )

    # Post-history instructions / jailbreak
    blocks["postHistoryInstructions"] = resolve(
        char_data.get("post_history_instructions", "") or preset.get("post_history_instructions", ""),
        **macro_kwargs,
    )

    # ── Calculate token costs ───────────────────────────────────────────
    block_costs: dict[str, int] = {}
    fixed_total = 0
    for label, content in blocks.items():
        cost = count_tokens(content) if content else 0
        block_costs[label] = cost
        fixed_total += cost

    # ── Trim dialogue examples if they eat too much budget ──────────────
    examples_budget = max(budget // 6, 200)  # cap examples at ~16% of budget
    if block_costs.get("dialogueExamples", 0) > examples_budget:
        # Truncate examples to fit
        examples = blocks["dialogueExamples"]
        starts = list(re.finditer(r'<START>', examples))
        if len(starts) > 1:
            # Keep as many <START> blocks as fit
            kept = ""
            for i, m in enumerate(starts):
                end = starts[i + 1].start() if i + 1 < len(starts) else len(examples)
                chunk = examples[m.start():end]
                if count_tokens(kept + chunk) <= examples_budget:
                    kept += chunk
                else:
                    break
            blocks["dialogueExamples"] = kept
            block_costs["dialogueExamples"] = count_tokens(kept)
            fixed_total = sum(block_costs.values())

    # ── Chat history trimming ───────────────────────────────────────────
    # Current user message cost
    user_msg_cost = count_tokens(user_message) + 4 if user_message else 0
    history_budget = budget - fixed_total - user_msg_cost

    trimmed_history = []
    history_tokens = 0
    for msg in reversed(chat_history):
        msg_cost = count_tokens(msg.get("content", "")) + 4
        if history_tokens + msg_cost > history_budget:
            break
        trimmed_history.insert(0, msg)
        history_tokens += msg_cost

    block_costs["chatHistory"] = history_tokens
    block_costs["userMessage"] = user_msg_cost

    # ── Assemble system prompt ──────────────────────────────────────────
    system_parts = []
    for label in DEFAULT_BLOCK_ORDER:
        if label == "chatHistory":
            continue  # chat history goes into messages, not system
        content = blocks.get(label, "")
        if content and content.strip():
            system_parts.append(content.strip())

    system_prompt = "\n\n".join(system_parts)

    # ── Assemble messages ───────────────────────────────────────────────
    messages = []
    messages.append({"role": "system", "content": system_prompt})

    for msg in trimmed_history:
        messages.append({
            "role": msg.get("role", "user"),
            "content": resolve(msg.get("content", ""), **macro_kwargs),
        })

    if user_message:
        messages.append({
            "role": "user",
            "content": resolve(user_message, **macro_kwargs),
        })

    # ── Metadata ────────────────────────────────────────────────────────
    total_used = fixed_total + history_tokens + user_msg_cost
    metadata = {
        "context_limit": context_limit,
        "max_response": max_response,
        "budget": budget,
        "total_used": total_used,
        "remaining": budget - total_used,
        "blocks": block_costs,
        "history_turns_kept": len(trimmed_history),
        "history_turns_total": len(chat_history),
        "history_trimmed": len(chat_history) - len(trimmed_history),
        "activated_lore_count": len(activated_lore),
        "activated_lore_names": [
            e.get("comment", e.get("key", ["?"])) for e in activated_lore
        ],
    }

    return {
        "system": system_prompt,
        "messages": messages,
        "metadata": metadata,
    }


# Need re for example trimming
import re
