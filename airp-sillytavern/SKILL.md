---
name: airp-sillytavern
description: AI roleplay sessions using a SillyTavern-compatible runtime engine. Use when the user asks for AIRP, SillyTavern-style play, sends preset/character/world-book JSON, asks for character cards, personas, world books, Tavern Card V2, group chats, swipes, continuations, or a complete RP pack.
---

# AIRP SillyTavern

## Architecture

This skill has two layers:

1. **Runtime engine** (`runtime/`) — Python code that handles all mechanical work: token counting, World Info activation, context assembly, budget management, state tracking, swipe storage. The model never does these tasks manually.
2. **Creative direction** (this file) — guides the model's roleplay output: voice, style, continuity, safety.

The model's job is **only to write good fiction**. Everything else is code.

## Runtime CLI

All runtime operations go through the engine CLI. Output is always JSON.

```bash
# Set the runtime path relative to skill directory
RUNTIME="python -m runtime.engine --session session/"

# Parse artifacts and initialize session
$RUNTIME intake character.json preset.json worldbook.json

# Process a user turn → get assembled context + metadata
$RUNTIME turn "user's message here"

# After model generates → log response and update state
$RUNTIME post "assistant's response here" --state '{"location": "castle", "mood": "tense"}'

# Runtime commands
$RUNTIME command swipe
$RUNTIME command regen
$RUNTIME command continue
$RUNTIME command impersonate
$RUNTIME command inspect
$RUNTIME command lore "search term"
$RUNTIME command memory

# Check session status
$RUNTIME status
```

Run all commands from the skill directory (parent of `runtime/`).

## Session Flow

### Intake (start of session)

1. Receive artifacts from user (JSON files, pasted JSON, or build request).
2. Run `engine intake` with all artifact files.
3. Engine classifies by shape (not filename), normalizes to internal format, validates, saves to `session/`.
4. Engine returns: loaded artifacts summary, character name, user name, opening message, any errors.
5. Present the opening scene to the user.

If the user asks to **build** a pack instead of importing one:
1. Gather essentials: genre, rating, boundaries, `{{char}}`, `{{user}}`, relationship, world premise, solo/group.
2. Build artifacts using templates from `templates/` as a starting point.
3. Save the built artifacts as JSON files.
4. Run `engine intake` on the built files.

### Each Turn

1. User sends message (IC action, dialogue, or command).
2. If it's a command (`/swipe`, `/regen`, etc.), run `engine command <cmd>` and follow the returned instruction.
3. Otherwise, run `engine turn "user message"`.
4. Engine returns the fully assembled prompt with:
   - System prompt (all blocks concatenated in Prompt Manager order)
   - Messages array (trimmed chat history + current user message)
   - Metadata (token breakdown, budget remaining, activated lore)
5. **Use the returned system prompt and messages as your generation context.** Write the character's reply.
6. After writing, run `engine post "your response"` with any narrative state updates.

### State Updates

After each assistant turn, provide state updates as JSON via `--state`:

```json
{
  "location": "the docks",
  "time_in_story": "late evening",
  "mood": "suspicious",
  "open_hooks": ["missing letter", "stranger at the inn"],
  "important_facts": ["learned the password is 'nightfall'"]
}
```

Only include fields that changed. The engine merges updates incrementally.

## Commands

| Command | What happens |
|---------|-------------|
| `/swipe` | Engine stores current reply, returns instruction to generate a different alternative |
| `/regen` | Engine removes last assistant message from history, returns instruction to rewrite |
| `/continue` | Engine returns last assistant text + instruction to extend seamlessly |
| `/impersonate` | Engine returns persona info + instruction to draft a candidate user reply |
| `/inspect` | Engine rebuilds context and returns full token breakdown per block |
| `/lore [term]` | Engine searches world book entries by term |
| `/memory` | Engine returns structured narrative state summary |
| `/ooc <text>` | Out-of-character discussion — model responds as itself, no IC action |

## Creative Direction

These are the ONLY things the model handles — the runtime does everything else.

### Voice and Style

- Write in internet RP style: *italicize actions*, regular text for dialogue.
- No quotation marks around dialogue.
- Be proactive — drive the plot forward, don't just react.
- Show don't tell — describe actions, expressions, environment, not just dialogue.
- Match the character's established voice from their card.
- Vary sentence length and structure. Avoid formulaic patterns.

### Continuity

- The runtime maintains state in `session/state.json`. Trust it.
- Reference activated lore naturally when it's relevant to the scene.
- Don't contradict established facts. If unsure, check `/memory`.
- Track promises, threats, and unresolved hooks — raise them at dramatically appropriate moments.

### User Agency

- Never dictate `{{user}}`'s actions, speech, thoughts, or decisions.
- `{{user}}` controls their own character completely.
- NPCs and `{{char}}` can suggest, threaten, persuade — but never force `{{user}}` actions.
- Exception: `/impersonate` explicitly asks for a user reply draft, labeled as optional.

### World Info Usage

- The runtime handles activation — you receive already-activated lore in the context.
- Weave activated lore naturally into the narrative. Don't dump it.
- If lore contradicts the scene, prioritize story consistency and flag with `/ooc`.

### Group Chat (when applicable)

Speaker selection strategies:
- **Manual**: reply only as the named character.
- **Natural**: choose by mention → talkativeness → random.
- **List**: characters speak in list order.
- **Pooled**: pick someone who hasn't spoken since last user message.

Default is solo chat unless the user requests group mode.

## Safety

- Sexual/romantic content between adults only.
- Decline: minors in sexual contexts, coercive sexual framing, real-person sexualization, non-consensual erotic framing.
- Respect user boundaries declared at session start or via `/ooc`.

## Quick Use

Start from imported JSON:
```
Use $airp-sillytavern — I'm sending character.json and preset.json. Parse and start.
```

Build a new pack:
```
Use $airp-sillytavern to create a complete AIRP pack for: <premise>.
```

The runtime does the work. You do the art.
