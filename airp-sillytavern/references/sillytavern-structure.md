# SillyTavern Structure Notes

Use this reference when a task needs SillyTavern compatibility or a close Codex AIRP recreation.

## Sources Checked

- Main repository: https://github.com/SillyTavern/SillyTavern
- Release default OpenAI preset: https://github.com/SillyTavern/SillyTavern/blob/release/default/content/presets/openai/Default.json
- Prompt Manager: https://docs.sillytavern.app/usage/prompts/prompt-manager/
- Prompt building: https://docs.sillytavern.app/usage/prompts/
- Character Design: https://docs.sillytavern.app/usage/core-concepts/characterdesign/
- Personas: https://docs.sillytavern.app/usage/core-concepts/personas/
- World Info: https://docs.sillytavern.app/usage/core-concepts/worldinfo/
- Group Chats: https://docs.sillytavern.app/usage/core-concepts/groupchats/
- Macros: https://docs.sillytavern.app/usage/core-concepts/macros/
- STscript: https://docs.sillytavern.app/usage/st-script/
- Character Card V2 spec: https://github.com/malfoyslastname/character-card-spec-v2

## Current GitHub Facts

The release branch repository describes SillyTavern as a locally installed LLM frontend for power users. It offers a unified UI for many LLM APIs, mobile-friendly layout, Visual Novel mode, image generation integration, TTS, WorldInfo, customizable UI, prompt controls, and extension growth. The repository is AGPL-3.0 and the latest release shown during this check was 1.17.0 on March 28, 2026.

## Prompt Manager Model

SillyTavern Chat Completion presets contain prompt blocks and an order list. The release default OpenAI preset includes:

```text
main
worldInfoBefore
personaDescription
charDescription
charPersonality
scenario
enhanceDefinitions
nsfw / Auxiliary Prompt
worldInfoAfter
dialogueExamples
chatHistory
jailbreak / Post-History Instructions
```

Default main prompt:

```text
Write {{char}}'s next reply in a fictional chat between {{char}} and {{user}}.
```

Default sampling from the GitHub preset uses temperature 1, top_p 1, frequency_penalty 0, presence_penalty 0, repetition_penalty 1, OpenAI context 4095, max tokens 300, streaming enabled, seed -1.

For Codex AIRP, preserve the block order and use labels even when the final prompt is Markdown.

## Macro Model

Macros are placeholders resolved during prompt construction. Core AIRP macros:

- `{{char}}`: active character name
- `{{user}}`: active persona name
- `{{scenario}}`: scenario text
- `{{personality}}`: personality text
- `{{original}}`: original prompt content inside prompt override fields
- `{{outlet::Name}}`: World Info outlet content

Codex cannot execute SillyTavern's macro engine. Resolve these manually when building or running a pack.

## Character Card V2

SillyTavern only requires a character name to chat, but a serious AIRP card needs permanent and volatile parts.

Permanent character tokens:

- character name
- description
- personality
- scenario

Volatile or conditional parts:

- first message, used at chat start
- alternate greetings, used as start swipes
- example messages, retained while context allows
- character note at depth
- system prompt override
- post-history instructions override
- creator metadata
- embedded character book

Recommended JSON:

```json
{
  "spec": "chara_card_v2",
  "spec_version": "2.0",
  "data": {
    "name": "",
    "description": "",
    "personality": "",
    "scenario": "",
    "first_mes": "",
    "mes_example": "<START>\n{{user}}: ...\n{{char}}: ...",
    "creator_notes": "",
    "system_prompt": "",
    "post_history_instructions": "",
    "alternate_greetings": [],
    "character_book": {
      "name": "",
      "description": "",
      "scan_depth": 2,
      "token_budget": 512,
      "recursive_scanning": true,
      "extensions": {},
      "entries": []
    },
    "tags": [],
    "creator": "",
    "character_version": "1.0",
    "extensions": {}
  }
}
```

## Persona Model

A persona is the user's active identity: display name, avatar, and optional description. Persona description may be inserted in Prompt Manager, Author's Note, or chat depth. In Codex, keep persona fields explicit:

```json
{
  "name": "",
  "title": "",
  "description": "",
  "position": "prompt_manager",
  "locks": {
    "default": false,
    "chat": false,
    "character": ""
  },
  "lorebook": ""
}
```

When converting a character to a persona, swap macro meanings carefully because `{{user}}` and `{{char}}` reverse perspective.

## World Info Model

World Info inserts relevant text dynamically when activation conditions match. Keys and titles are activation metadata; only Content is inserted. Therefore every entry content must be standalone.

Entry shape:

```json
{
  "uid": 1,
  "key": ["Proper Name", "Unique Alias"],
  "keysecondary": [],
  "comment": "Memo for editor only",
  "content": "Standalone lore inserted into context.",
  "constant": false,
  "vectorized": false,
  "selective": false,
  "selectiveLogic": 0,
  "order": 100,
  "position": 1,
  "disable": false,
  "excludeRecursion": false,
  "preventRecursion": false,
  "delayUntilRecursion": false,
  "probability": 100,
  "useProbability": true,
  "depth": 0,
  "role": 0,
  "group": "",
  "groupOverride": false,
  "groupWeight": 100,
  "scanDepth": null,
  "caseSensitive": null,
  "matchWholeWords": null,
  "automationId": "",
  "sticky": 0,
  "cooldown": 0,
  "delay": 0,
  "triggers": []
}
```

Common positions:

- before character definitions
- after character definitions
- before or after example messages
- top or bottom of Author's Note
- in-chat at depth
- outlet

Activation policy:

- Scan recent chat according to scan depth.
- Include names when name-sensitive activation is desired.
- Insert constant entries first.
- Favor directly triggered entries over recursively triggered entries.
- Use higher order values closer to the end of context.
- Use whole-word matching for English-style single-word keys.
- Turn whole-word matching off for Chinese or Japanese content.
- Use recursion for linked lore, with a budget.

## Group Chat Model

Group chats share history across members. Default generation swaps the active speaker's card into context. Joined-card mode combines descriptions, scenarios, personalities, examples, and depth prompts for all selected members.

Speaker strategies:

- Manual: named member only.
- Natural: mention match, then talkativeness, then random.
- List: member list order.
- Pooled: one member who has not spoken since the latest user turn.

For Codex, keep group state:

```json
{
  "members": [],
  "strategy": "natural",
  "generation_mode": "swap_card",
  "muted": [],
  "talkativeness": {},
  "last_speakers_since_user": []
}
```

## Codex Runtime Commands

Use these textual commands to mimic SillyTavern controls:

- `/ooc <text>`: meta discussion.
- `/lore <term>`: show activated or matching lore.
- `/lore-set <entry>`: update chat lore when the user requests persistence.
- `/memory`: show current state summary.
- `/memory-set <fact>`: update memory.
- `/swipe [n]`: produce alternate assistant reply candidates.
- `/regen`: rewrite latest assistant message from the same state.
- `/continue`: extend latest assistant message.
- `/impersonate`: draft one optional user reply.
- `/preset`: show prompt rules.
- `/card`: show active character facts.
- `/persona`: show active user persona.
- `/inspect`: show prompt assembly blocks and active lore names.

## Faithful Codex Play Loop

1. Resolve macros for current `{{char}}` and `{{user}}`.
2. Select group speaker when needed.
3. Scan latest chat for World Info keys.
4. Add forced, timed, and recursive lore within budget.
5. Assemble prompt blocks in the preset order.
6. Generate one assistant turn.
7. Update compact memory after meaningful state changes.
8. Store alternate replies as swipes when requested.

## Import And Auto Start

When a user pastes or attaches SillyTavern JSON, classify by shape rather than filename.

Preset indicators:

- `prompts`
- `prompt_order`
- `chat_completion_source`
- `openai_model`
- sampling fields such as `temperature`, `top_p`, `frequency_penalty`, `presence_penalty`, `max_tokens`, `stream_openai`

Character card indicators:

- `spec: "chara_card_v2"`
- `spec_version`
- `data.name`
- `data.first_mes`
- legacy fields: `name`, `description`, `personality`, `scenario`, `first_mes`, `mes_example`

World book indicators:

- top-level `entries`
- entry fields such as `key`, `keys`, `keysecondary`, `content`, `constant`, `selective`, `order`, `position`, `disable`, `probability`, `scanDepth`, `sticky`, `cooldown`, `delay`

Persona indicators:

- `name`
- `description`
- user-facing identity text
- persona lock or avatar metadata

Auto-start with this minimum state:

```json
{
  "preset": {},
  "character": {},
  "persona": {"name": "{{user}}", "description": ""},
  "world_book": {"entries": []},
  "memory": {
    "time": "",
    "place": "",
    "state": "",
    "open_hooks": []
  },
  "swipes": []
}
```

Start from `data.first_mes`, `first_mes`, or the selected alternate greeting. If the opening is empty, create a neutral in-character opening from scenario plus character voice and mark it as generated.

## Quality Checks

- Required artifacts exist.
- JSON parses.
- Prompt order matches the preset.
- Character description, personality, and scenario are separate.
- First message teaches tone and action format.
- Example messages use `<START>`.
- Persona has a clear injected position.
- World Info content stands alone.
- Lore keys are narrow.
- Group speaker rules are explicit.
- Runtime commands are listed.
- Adult and consent boundaries are explicit.
