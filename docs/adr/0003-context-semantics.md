# ADR-0003: Context Semantics — Formal Definition of PromptBuilder Context Providers

**Status**: Complete  
**Date**: 2026-07-18  
**Supersedes**: N/A  

---

## 1. Context

The PromptBuilder architecture (ADR-0001) establishes that system prompts are assembled from independent `ContextProvider` components. Each provider contributes a single `ContextBlock` with explicit metadata (name, priority, mutability, content).

This ADR formally defines the **semantics** of every context provider — what it owns, what it must not do, and how it relates to other providers. The goal is to make each provider:

- **Modular**: Can be added/removed/reordered without touching other providers
- **Independently testable**: No hidden dependencies on other providers' output
- **Impossible to misuse**: Boundaries enforced by type system and documentation

Character Memory (Step 3) and the Canon Framework (Step 4) will be implemented **only after** these semantics are agreed upon.

---

## 2. Provider Registry (Single Source of Truth)

The authoritative provider ordering is declared in `utils/prompt_builder.py::_get_default_providers()`:

| Priority | Provider                        | Mutability    | Status               |
|:--------:|:--------------------------------|:--------------|:---------------------|
|    10    | `SystemContextProvider`         | IMMUTABLE     | Implemented          |
|    20    | `PersonaContextProvider`        | IMMUTABLE     | Implemented          |
|  **25**  | **`CanonContextProvider`**      | **IMMUTABLE** | **Implemented**      |
|    30    | `ConversationHistoryProvider`   | MUTABLE       | Implemented          |
|    40    | `UserMemoryProvider`            | MUTABLE       | Implemented          |
|    50    | `CharacterMemoryProvider`       | MUTABLE       | **Implemented**      |
|  **55**  | **`GuildWorldContextProvider`** | **MUTABLE**   | **Implemented**      |
|    60    | `PersonaKnowledgeBaseProvider`  | IMMUTABLE     | Implemented          |

> **Rule**: New providers register via priority in `_get_default_providers()`. No other code determines ordering.

---

## 3. Formal Provider Definitions

### 3.1 SystemContextProvider (Priority 10, IMMUTABLE)

| Attribute          | Definition                                                                                                                             |
|:-------------------|:---------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides model-level system instructions that apply regardless of persona. Currently extracts `system_instructions` from persona data. |
| **Input**          | `PromptBuildContext.persona_data["system_instructions"]`                                                                               |
| **Output**         | `<system_instructions>...</system_instructions>` block                                                                                 |
| **Mutability**     | IMMUTABLE — Changes only when persona config changes (admin action)                                                                    |
| **Lifetime**       | Session-bound to active persona; persists across conversations                                                                         |
| **Authority**      | Highest — Defines hard constraints on model behavior (safety, format, reasoning)                                                       |
| **Ownership**      | `utils/persona.py` (data), `utils/prompt_builder_providers.py` (assembly)                                                              |
| **Boundaries**     | MUST NOT include persona personality, knowledge, or conversation state. MUST NOT depend on user, channel, or guild context.            |

---

### 3.2 PersonaContextProvider (Priority 20, IMMUTABLE)

| Attribute          | Definition                                                                                                                                                                 |
|:-------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides the core persona definition: role, background, beliefs, language style.                                                                                           |
| **Input**          | `PromptBuildContext.persona_data` fields: `core_personality`, `background`, `beliefs`, `language`                                                                          |
| **Output**         | XML blocks: `<role>`, `<background>`, `<beliefs>`, `<language>`                                                                                                            |
| **Mutability**     | IMMUTABLE — Changes only when persona is switched or edited via `/setpersona`                                                                                              |
| **Lifetime**       | Session-bound to active persona; persists across conversations                                                                                                             |
| **Authority**      | Defines *who* the character is — the immutable identity layer                                                                                                              |
| **Ownership**      | `utils/persona.py` (data & assembly logic), `utils/prompt_builder_providers.py` (provider)                                                                                 |
| **Boundaries**     | MUST NOT include system instructions (priority 10). MUST NOT include conversation history, user facts, or retrieved knowledge. MUST NOT adapt based on channel/guild/user. |

---

### 3.3 CanonContextProvider (Priority 25, IMMUTABLE) — **Implemented**

| Attribute          | Definition                                                                                                                                                                                                  |
|:-------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides modular, immutable canon blocks that explain the *why* behind persona behavior. Replaces monolithic persona with composable canon fragments.                                                       |
| **Input**          | Structured canon store (new subsystem — see Canon Framework ADR) keyed by `persona_id`                                                                                                                      |
| **Output**         | Ordered canon blocks: `<core_identity>`, `<core_beliefs>`, `<core_motivations>`, `<behavioral_rules>`, `<world_assumptions>`, `<canon_explanations>`                                                        |
| **Mutability**     | IMMUTABLE — Canon is authored/approved, not learned. Changes require explicit admin action.                                                                                                                 |
| **Lifetime**       | Permanent for a given persona version; versioned with persona snapshots                                                                                                                                     |
| **Authority**      | Explains the *reasoning* behind behavior. Higher authority than Persona for behavioral consistency.                                                                                                         |
| **Ownership**      | New `utils/canon.py` module; `utils/prompt_builder_providers.py` (provider)                                                                                                                                 |
| **Boundaries**     | MUST NOT contain conversation-specific state. MUST NOT contain user-specific facts. MUST NOT be generated by LLM — only authored. Timeline divergence happens *around* canon, never *by overwriting* canon. |

> **Rationale for Priority 25**: Canon is between System (hard constraints) and Persona (identity expression). It provides the reason for Persona behavior. The model receives: Constraints → Reasoning → Identity → Context.

---

### 3.4 ConversationHistoryProvider (Priority 30, MUTABLE)

| Attribute          | Definition                                                                                                                                                                                                             |
|:-------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides recent conversation context from Freesona-owned ConversationManager.                                                                                                                                          |
| **Input**          | `PromptBuildContext.guild_id`, `channel_id`, `user_id` → `ConversationManager.build_conversation_context()`                                                                                                            |
| **Output**         | Formatted block: `Recent Conversation Summary` + `Recent Messages`                                                                                                                                                     |
| **Mutability**     | MUTABLE — Updates on every user/assistant message                                                                                                                                                                      |
| **Lifetime**       | Per `(guild_id, channel_id, user_id)` scope; TTL default 1 hour; max 20 messages / 4000 tokens                                                                                                                         |
| **Authority**      | Represents *what was said* in this session. Ground truth for short-term continuity.                                                                                                                                    |
| **Ownership**      | `utils/conversation.py` (storage & logic), `utils/prompt_builder_providers.py` (provider)                                                                                                                              |
| **Boundaries**     | MUST NOT summarize (summarization is a separate subsystem). MUST NOT extract facts (that's User Memory). MUST NOT know about persona, PKB, or Character Memory. MUST require `channel_id` — no fallback to `guild_id`. |

---

### 3.5 UserMemoryProvider (Priority 40, MUTABLE)

| Attribute          | Definition                                                                                                                                                                                       |
|:-------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides long-term facts *about the user* extracted from conversation history.                                                                                                                   |
| **Input**          | `PromptBuildContext.guild_id`, `user_id`, `username` → `memory.get_user_facts_prompt()`                                                                                                          |
| **Output**         | `[Known facts about {username}]` block with bullet-list facts                                                                                                                                    |
| **Mutability**     | MUTABLE — Facts added/updated via background extraction; importance-scored; top 20 retained                                                                                                      |
| **Lifetime**       | Persistent (SQLite); survives restarts; per `(guild_id, user_id)`                                                                                                                                |
| **Authority**      | Represents *what the persona knows about the user* across sessions                                                                                                                               |
| **Ownership**      | `utils/memory.py` (storage & extraction), `utils/prompt_builder_providers.py` (provider)                                                                                                         |
| **Boundaries**     | MUST NOT store facts *about* the persona (that's PKB). MUST NOT store shared experiences (that's Character Memory). MUST NOT include conversation history. Scope is strictly user-centric facts. |

---

### 3.6 CharacterMemoryProvider (Priority 50, MUTABLE) — **Implemented**

| Attribute          | Definition                                                                                                                                                                                                                                                                                                                                                                                                                         |
|:-------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides persistent shared history *between the persona and the user*: promises, shared experiences, recurring jokes, unfinished activities, relationship progression, persistent decisions.                                                                                                                                                                                                                                       |
| **Input**          | `PromptBuildContext.guild_id`, `user_id`, `persona_id` → `CharacterMemoryStore.get_context()`                                                                                                                                                                                                                                                                                                                                      |
| **Output**         | `[Character Memory]` block with structured entries (type, content, importance, timestamp)                                                                                                                                                                                                                                                                                                                                          |
| **Mutability**     | MUTABLE — Memories added/updated/deleted via extraction pipeline; importance-scored; budgeted                                                                                                                                                                                                                                                                                                                                      |
| **Lifetime**       | Persistent (new storage); per `(guild_id, user_id, persona_id)` triple                                                                                                                                                                                                                                                                                                                                                             |
| **Authority**      | Represents *the relationship history* — what they've been through together                                                                                                                                                                                                                                                                                                                                                         |
| **Ownership**      | New `utils/character_memory.py` (storage, extraction, retrieval), `utils/prompt_builder_providers.py` (provider)                                                                                                                                                                                                                                                                                                                   |
| **Boundaries**     | **MUST NOT** store canonical facts (PKB). **MUST NOT** store user facts (User Memory). **MUST NOT** store conversation history (ConversationManager). **MUST** consume ConversationManager as *source* for extraction. **MUST** handle persona switches correctly (memories scoped to persona). **MUST** be scoped to guild (not channel) — a character's relationship with a user persists across channels within the same guild. |

---

### 3.7 GuildWorldContextProvider (Priority 55, MUTABLE) — **Implemented**

| Attribute          | Definition                                                                                                                                                                                                |
|:-------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides environmental context: the Discord guild as the character's "world" — server name, channel context, active members, local norms.                                                                 |
| **Input**          | `PromptBuildContext.guild_id`, `channel_id` → Discord API (guild name, channel name, topic, member count, etc.)                                                                                           |
| **Output**         | `[Guild Context]` block: `Server: {name}`, `Channel: {name} ({topic})`, `Population: {count}`                                                                                                             |
| **Mutability**     | MUTABLE — Changes as guild/channel metadata changes                                                                                                                                                       |
| **Lifetime**       | Request-scoped (fetched fresh each generation)                                                                                                                                                            |
| **Authority**      | Environmental grounding — where the conversation is happening *right now*                                                                                                                                 |
| **Ownership**      | New `utils/guild_world.py` (provider), `utils/prompt_builder_providers.py` (provider)                                                                                                                     |
| **Boundaries**     | MUST NOT store history (that's Conversation/Character Memory). MUST NOT store user facts. MUST NOT require special permissions beyond `guild` and `channel` intents. This is *environment*, not *memory*. |

---

### 3.8 PersonaKnowledgeBaseProvider (Priority 60, IMMUTABLE)

| Attribute          | Definition                                                                                                                                                  |
|:-------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility** | Provides retrieved canonical knowledge from the Persona Knowledge Base (RAG).                                                                               |
| **Input**          | `PromptBuildContext.user_message`, `persona_id`, `kb_enabled`, `kb_top_k` → `chroma.query_knowledge()`                                                      |
| **Output**         | `Relevant Canonical Context` block with numbered entries + metadata (source, type, speaker, canon_level)                                                    |
| **Mutability**     | IMMUTABLE at query time — KB entries are authored/ingested, not generated                                                                                   |
| **Lifetime**       | Persistent (ChromaDB); per `persona` (collection filter)                                                                                                    |
| **Authority**      | Canonical truth about the persona's source material                                                                                                         |
| **Ownership**      | `utils/chroma.py` (storage & retrieval), `utils/generation.py` (retrieve_knowledge_context), `utils/prompt_builder_providers.py` (provider)                 |
| **Boundaries**     | MUST NOT include conversation history. MUST NOT include user facts. MUST NOT include character memories. Retrieval is *passive* — no LLM calls in provider. |

---

## 4. Cross-Provider Boundary Rules

These rules are **architectural invariants**. Violations are bugs.

| Rule                                                   | Enforcement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
|:-------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **No provider reads another provider's output**        | Providers receive only `PromptBuildContext` (primitives + raw persona_data). No `ContextBlock` passing.                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **No provider modifies shared state during `build()`** | `build()` is `async` but must be pure w.r.t. other providers. Side effects (DB writes) happen in separate pipelines.                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Mutability classification is authoritative**         | `ContextBlock.mutability` determines token budget allocation, caching, and debugging. Never lie.                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **Priority is the only ordering mechanism**            | No `if provider == "x": move_before("y")` logic anywhere.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| **Framework-agnostic**                                 | Zero `discord` imports in `prompt_builder.py` or `prompt_builder_providers.py`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Provider-agnostic**                                  | Zero provider-specific logic (Gemini/OpenAI/etc.) in any provider.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **No provider establishes canonical truth**            | **Only `CanonContextProvider` (priority 25) and `PersonaKnowledgeBaseProvider` (priority 60) may define objective facts about the persona.** All other providers MUST only describe: *what happened* (Conversation History), *what the user said* (Conversation History), *what the character promised* (Character Memory), *where they are* (Guild World Context), *what the current environment is* (Guild World Context). Canonical facts about the character's origin, beliefs, motivations, and immutable traits belong exclusively to Canon/PKB. |

---

## 5. Context Block Metadata Contract

Every `ContextBlock` returned by `ContextProvider.build()` **must** populate:

```python
@dataclass
class ContextBlock:
    name: str              # Provider identifier (e.g., "persona")
    priority: int          # Assembly priority (lower = earlier)
    mutability: Mutability # IMMUTABLE | MUTABLE | PLACEHOLDER
    content: str           # Rendered text (may be empty)
```

**Consumers** (debug UI, token accounting, selective context) rely on these fields being accurate.

---

## 6. PromptBuildContext — The Shared Input Contract

`PromptBuildContext` is a **data-only** carrier. It contains **only** what providers need to do their job.

### Current Fields (Implemented)

| Field                       | Type            | Providers Needing It                                              |
|:----------------------------|:----------------|:------------------------------------------------------------------|
| `guild_id`                  | `Optional[int]` | ConversationHistory, UserMemory, CharacterMemory, GuildWorld, PKB |
| `channel_id`                | `Optional[int]` | ConversationHistory, GuildWorld                                   |
| `user_id`                   | `Optional[int]` | ConversationHistory, UserMemory, CharacterMemory                  |
| `username`                  | `str`           | UserMemory, CharacterMemory                                       |
| `persona_id`                | `str`           | CharacterMemory, PKB                                              |
| `persona_data`              | `dict`          | System, Persona, Canon                                            |
| `current_persona_assembled` | `str`           | (Legacy compat — deprecated)                                      |
| `apply_persona`             | `bool`          | System, Persona, Canon                                            |
| `kb_enabled`                | `bool`          | PKB                                                               |
| `kb_top_k`                  | `int`           | PKB                                                               |
| `user_message`              | `str`           | PKB (query)                                                       |
| `instruction_prefix`        | `str`           | (Used by generation.py, not providers)                            |

### Fields Required for Planned Providers

| Field                               | Type            | Provider   | Status                                                                          |
|:------------------------------------|:----------------|:-----------|:--------------------------------------------------------------------------------|
| `guild_id`                          | `Optional[int]` | GuildWorld | ✅ Exists                                                                        |
| `channel_id`                        | `Optional[int]` | GuildWorld | ✅ Exists                                                                        |
| (Discord `guild`/`channel` objects) | —               | GuildWorld | **Not in context** — provider must fetch via bot reference or separate accessor |

> **Design Decision**: `GuildWorldContextProvider` will need access to Discord guild/channel metadata. Since `PromptBuildContext` is framework-agnostic, the provider will receive a `GuildWorldAccessor` protocol (injected at build time) rather than raw Discord objects.

---

## 7. Token Budget & Mutability Interaction

| Mutability    | Token Budget Behavior                                  | Caching                                       |
|:--------------|:-------------------------------------------------------|:----------------------------------------------|
| `IMMUTABLE`   | Fixed per persona/session; cache aggressively          | Full cache (content hash keyed by persona_id) |
| `MUTABLE`     | Dynamic; counted against remaining budget each request | No cache (changes every request)              |
| `PLACEHOLDER` | Zero budget; skipped in assembly                       | N/A                                           |

**Budget Order** (when budget exhausted, drop lowest-priority MUTABLE blocks first):

1. IMMUTABLE (10, 20, 25, 60) — **Never dropped**
2. MUTABLE (30, 40, 50, 55) — Dropped in reverse priority order

---

## 8. Implementation Sequence (Enforced by This ADR)

| Step    | Deliverable                                             | Status       |
|:--------|:--------------------------------------------------------|:-------------|
| **3.1** | `CanonContextProvider` + `utils/canon.py`               | ✅ Completed |
| **3.2** | `CharacterMemoryProvider` + `utils/character_memory.py` | ✅ Completed |
| **3.3** | `GuildWorldContextProvider` + `utils/guild_world.py`    | ✅ Completed |
| **3.4** | Token budget integration in `PromptBuilder.build()`     | ✅ Completed |

> **All provider implementations complete.** This ADR documents the final architecture.

---

## 9. Acceptance Criteria for This ADR

- [x] All 8 providers defined with complete semantics (responsibility, mutability, lifetime, authority, ownership, boundaries)
- [x] Priority ordering justified and documented
- [x] Cross-provider boundary rules explicitly stated
- [x] `PromptBuildContext` contract covers all current + planned providers
- [x] Token budget / mutability interaction defined
- [x] All providers implemented and integrated

---

## 10. References

- ADR-0001: PromptBuilder Architecture (`docs/adr/0001-prompt-builder.md`)
- ADR-0002: ConversationManager (`docs/adr/0002-conversation-manager.md`)
- `utils/prompt_builder.py` — Core architecture
- `utils/prompt_builder_providers.py` — Current provider implementations
- `docs/architecture.md` — System architecture (to be updated post-A
DR)

---

## 11. Logging Section Semantics (`utils/logging_utils.py`)

Freesona's logging system supports granular log sections to control verbosity per subsystem. Each section maps to a set of logger name prefixes.

### Section Definitions

| Section | Config Key | Logger Prefixes | Default | Description |
|:--------|:-----------|:----------------|:--------|:------------|
| General | `log_section_general` | `main`, `cogs`, `utils` | ✅ Enabled | Bot lifecycle, cog loading, general events |
| Config | `log_section_config` | `utils.config`, `cogs.system.config` | ❌ Disabled | Configuration changes |
| AI | `log_section_ai` | `utils.providers`, `utils.generation`, `utils.prompt_builder*`, `cogs.ai` | ✅ Enabled | AI provider calls, generation, prompt assembly |
| Memory | `log_section_memory` | `utils.memory`, `utils.conversation`, `utils.character_memory`, `utils.canon`, `utils.chroma` | ❌ Disabled | Memory operations (conversation, facts, character, canon, KB) |
| Media | `log_section_media` | `cogs.media`, `utils.search` | ❌ Disabled | Media operations (MVSEP, yt-dlp, search) |
| Moderation | `log_section_moderation` | `cogs.moderation` | ❌ Disabled | Moderation actions (kick, ban, warn) |
| Security | `log_section_security` | `utils.security` | ✅ Enabled | Security checks (injection detection, URL validation) |
| Webhook | `log_section_webhook` | `fastapi_server` | ❌ Disabled | Webhook events (FastAPI/MVSEP) |

### Rules

1. **ERROR/CRITICAL always pass** — Regardless of section settings, ERROR and CRITICAL level logs are never filtered by the section filter.
2. **Section filter is applied to all handlers** — Console, file, and Discord handlers all use the same `SectionFilter`.
3. **Runtime changes** — Section enable/disable takes effect immediately via `refresh_section_filter()` without restart.
4. **Discord commands** — Owner-only `/logging` command group provides status, enable/disable/toggle, channel management, level setting, and test messages.
5. **Config panel** — Sections appear under "Logging Sections" category in `/config` panel.

### Logger Name Mapping

The mapping from logger name to section is prefix-based (longest match wins):

```python
LOGGER_SECTION_MAP = {
    "main": "general",
    "cogs": "general",
    "utils": "general",
    "utils.config": "config",
    "cogs.system.config": "config",
    "utils.providers": "ai",
    "utils.generation": "ai",
    "utils.prompt_builder": "ai",
    "utils.prompt_builder_providers": "ai",
    "cogs.ai": "ai",
    "utils.memory": "memory",
    "utils.conversation": "memory",
    "utils.character_memory": "memory",
    "utils.canon": "memory",
    "utils.chroma": "memory",
    "cogs.media": "media",
    "utils.search": "media",
    "cogs.moderation": "moderation",
    "utils.security": "security",
    "fastapi_server": "webhook",
}
```

This ensures predictable section assignment for all current and future loggers.

---

## 12. Guild World Context Channel Enumeration (`utils/guild_world.py`)

The `GuildWorldAccessor` protocol includes a `get_guild_channels(guild_id)` method that returns a list of `GuildChannelInfo` dataclasses. This enables KB 2.0 and other features to understand server structure without persisting it as memory.

### GuildChannelInfo Fields

| Field | Type | Description |
|:------|:-----|:------------|
| `id` | `int` | Channel snowflake ID |
| `name` | `str` | Channel name |
| `type` | `str` | Channel type (`text`, `voice`, `category`, `stage`, `forum`, `thread`) |
| `topic` | `Optional[str]` | Channel topic/description |
| `position` | `int` | Channel position in the list |
| `category_id` | `Optional[int]` | Parent category ID |
| `nsfw` | `bool` | Whether channel is marked NSFW |

### Design Principles

- **Not memory** — Channel list is fetched fresh from Discord's cache on each request
- **No persistence** — No database writes, no history, no cross-guild awareness
- **Protocol-based** — `GuildWorldAccessor` is a Protocol; `DiscordGuildWorldAccessor` is the Discord.py implementation; `NullGuildWorldAccessor` provides safe defaults for testing
- **KB 2.0 ready** — Enables tagging knowledge to specific channels, understanding server structure, and letting the persona reference other channels by name

### Usage

```python
from utils.guild_world import DiscordGuildWorldAccessor, GuildChannelInfo

accessor = DiscordGuildWorldAccessor(bot)
channels: list[GuildChannelInfo] = await accessor.get_guild_channels(guild_id)

for ch in channels:
    print(ch.format_for_prompt())  # e.g., "#general (General chat)", "#voice-chat [voice]"
```
