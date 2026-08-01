# Multi-Guild Identity Architecture Alignment Report

This document follows ASD-STE100 Simplified Technical English.

**Status**: Alignment Review  
**Date**: 2026-07-18  
**Related**: ADR-0003 (Context Semantics), architecture.md, architecture-review-v2.md

---

## 1. Executive Summary

This report evaluates the current Freesona architecture against the **Multi-Guild Identity with Local Context** philosophy described in the issue. The philosophy establishes that:

> Freesona should model a character that exists **through Discord**, not inside a single guild. The character has one persistent identity, but participates in multiple independent communities, just like a real Discord user.

**Overall Assessment**: The architecture is **well-aligned** with this philosophy. The provider-based prompt assembly (PromptBuilder) and explicit context scoping in each provider naturally enforce guild isolation without hardcoded logic in the generation pipeline.

---

## 2. Philosophy-to-Architecture Mapping

### 2.1 Canon is Global and Immutable ✅ ALIGNED

| Philosophy Requirement | Architecture Implementation | Status |
|:---|:---|:---|
| Single canonical identity across all guilds | `PersonaContextProvider` (priority 20, IMMUTABLE) uses `persona_data` only — no guild/channel/user context | ✅ |
| Immutable — changes only via admin action | `Mutability.IMMUTABLE` classification; cached aggressively | ✅ |
| Persona Knowledge Base is global to the persona | `PersonaKnowledgeBaseProvider` (priority 60, IMMUTABLE) filtered by `persona_id` only | ✅ |
| Canon Framework (planned) provides modular immutable blocks | `CanonContextProvider` (priority 25, IMMUTABLE) — planned in ADR-0003 Step 4 | 🟡 Planned |

**No changes needed.** The persona and PKB are already globally scoped by `persona_id`.

---

### 2.2 Conversation History is Local to Guild/Channel ✅ ALIGNED

| Philosophy Requirement | Architecture Implementation | Status |
|:---|:---|:---|
| Per-guild, per-channel, per-user | `ConversationManager` key: `(guild_id, channel_id, user_id)` | ✅ |
| No cross-guild leakage | Separate `ConversationState` per key; no shared state | ✅ |
| Provider-agnostic (not Gemini-specific) | `ConversationHistoryProvider` injects via system prompt for ALL providers | ✅ |
| TTL and budget enforcement | `conversation_ttl_seconds` (1h), `max_messages` (20), `token_budget` (4000) | ✅ |

**No changes needed.** ConversationManager already enforces strict guild/channel/user scoping.

---

### 2.3 Character Memory is Local to Guild (and User/Persona) 🟡 PARTIAL ALIGNMENT

| Philosophy Requirement | Architecture Implementation (ADR-0003) | Gap |
|:---|:---|:---|
| Local to current guild | ADR-0003 defines scope: `(guild_id, channel_id, user_id, persona_id)` | **Scope includes `channel_id`** — philosophy says "local to guild", ADR says per-channel |
| User/persona scope as designed | Includes `user_id` and `persona_id` | ✅ |
| Never stores canonical facts | ADR-0003 Boundaries: "MUST NOT store canonical facts (PKB)" | ✅ |
| Never replaces user memory | ADR-0003 Boundaries: "MUST NOT store user facts (User Memory)" | ✅ |
| Never replaces conversation history | ADR-0003 Boundaries: "MUST NOT store conversation history (ConversationManager)" | ✅ |
| Consumes ConversationManager for extraction | ADR-0003: "MUST consume ConversationManager as source for extraction" | ✅ |

**Gap Identified**: ADR-0003 scopes Character Memory to `(guild_id, channel_id, user_id, persona_id)` — i.e., **per-channel within a guild**. The philosophy states "local to the current guild (and user/persona scope as designed)" — implying **per-guild, not per-channel**.

**Recommendation**: Change Character Memory scope to `(guild_id, user_id, persona_id)` — remove `channel_id` from the key. A character's relationship with a user should persist across channels within the same guild, just as a real Discord user's relationship persists across channels.

---

### 2.4 Guild/Town Context is Purely Environmental and Request-Scoped ✅ ALIGNED

| Philosophy Requirement | Architecture Implementation (ADR-0003) | Status |
|:---|:---|:---|
| Environmental context (server name, channel context, local norms) | `GuildWorldContextProvider` (priority 55, MUTABLE) | ✅ Planned |
| Request-scoped (fetched fresh each generation) | ADR-0003: "Lifetime: Request-scoped (fetched fresh each generation)" | ✅ |
| Not memory — no persistence | ADR-0003: "MUST NOT store history... This is *environment*, not *memory*" | ✅ |
| No special permissions beyond guild/channel intents | ADR-0003: "MUST NOT require special permissions beyond `guild` and `channel` intents" | ✅ |

**No changes needed.** The planned design matches the philosophy.

---

### 2.5 Cross-Guild Isolation: No Automatic Leakage ✅ ALIGNED

| Philosophy Requirement | Architecture Enforcement |
|:---|:---|
| Conversation from Guild A never appears in Guild B | Separate `ConversationState` keys per `(guild_id, ...)` |
| User facts from Guild A never appear in Guild B | `UserMemoryProvider` queries `WHERE guild_id = ? AND user_id = ?` |
| Character memories from Guild A never appear in Guild B | CharacterMemoryProvider will scope by `guild_id` (per above fix) |
| PKB/Canon/Persona are global (intentionally shared) | Scoped only by `persona_id` — correct, these define the character |
| No hardcoded isolation logic in PromptBuilder/Generation | Each provider defines its own scope via `PromptBuildContext` fields |

**Architecture Principle**: Isolation is **emergent from provider scoping**, not enforced by a central gatekeeper. This satisfies the modularity requirement: *"Nothing about guild isolation... should be hardcoded into PromptBuilder or Generation."*

---

### 2.6 Discord-First Philosophy: Character as Guild Member ✅ ALIGNED

| Philosophy Requirement | Architecture Support |
|:---|:---|
| Not an omniscient AI treating Discord as one giant chat log | Context providers are explicitly scoped; no global conversation aggregation |
| No passive surveillance | ConversationManager only tracks channels where bot is addressed (via `on_message` filters in genai.py) |
| No DM-only relationships | Architecture assumes guild context (`guild_id` required for most providers); DMs not in current scope |
| Guilds are the primary world | `GuildWorldContextProvider` makes guild/channel metadata explicit environmental context |
| Personality consistent, social context changes | Persona/Canon (global) + Conversation/User Memory/Character Memory/Guild World (local) = consistent identity, contextual behavior |

---

## 3. Scope Comparison Matrix

| Context Source | Mutability | Current Scope Key | Philosophy Scope | Aligned? |
|:---|:---|:---|:---|:---|
| **System Instructions** | IMMUTABLE | `persona_id` | Global (persona) | ✅ |
| **Persona Definition** | IMMUTABLE | `persona_id` | Global (persona) | ✅ |
| **Canon Framework** | IMMUTABLE | `persona_id` | Global (persona) | 🟡 Planned |
| **Conversation History** | MUTABLE | `(guild_id, channel_id, user_id)` | Guild + Channel + User | ✅ |
| **User Memory (Facts)** | MUTABLE | `(guild_id, user_id)` | Guild + User | ✅ |
| **Character Memory** | MUTABLE | `(guild_id, channel_id, user_id, persona_id)` | **Guild + User + Persona** | 🟡 **Fix: remove channel_id** |
| **Guild World Context** | MUTABLE | `(guild_id, channel_id)` | Guild + Channel (request-scoped) | ✅ Planned |
| **Persona Knowledge Base** | IMMUTABLE | `persona_id` | Global (persona) | ✅ |

---

## 4. Required Adjustments Before Implementation

### 4.1 Character Memory Scope (ADR-0003 Update Required)

**Current ADR-0003 Definition** (Section 3.6):
```
Lifetime: Persistent (new storage); per (guild_id, channel_id, user_id, persona_id) quadruple
Input: PromptBuildContext.guild_id, channel_id, user_id, persona_id → CharacterMemoryStore.get_context()
```

**Required Change**: Remove `channel_id` from the scope key.
```
Lifetime: Persistent (new storage); per (guild_id, user_id, persona_id) triple
Input: PromptBuildContext.guild_id, user_id, persona_id → CharacterMemoryStore.get_context()
```

**Rationale**: A character's relationship with a user (promises, shared experiences, recurring jokes) should persist across channels within the same guild. A real Discord user doesn't "reset" their relationship when moving from #general to #roleplay.

**Impact**: 
- `PromptBuildContext` already has `guild_id`, `user_id`, `persona_id` — no new fields needed
- `CharacterMemoryProvider.build()` signature unchanged (just doesn't use `channel_id`)
- Storage schema: `PRIMARY KEY (guild_id, user_id, persona_id, memory_id)`

---

### 4.2 GuildWorldContextProvider Accessor Protocol (ADR-0003 Section 6)

ADR-0003 correctly identifies that `GuildWorldContextProvider` needs Discord guild/channel objects but `PromptBuildContext` is framework-agnostic. The design decision to inject a `GuildWorldAccessor` protocol at build time is sound.

**Implementation Note**: The accessor should be passed via `PromptBuilder` construction or a context extension, not via `PromptBuildContext` (which must remain framework-agnostic).

---

### 4.3 Token Budget Priority Order (ADR-0003 Section 7)

Current drop order for MUTABLE blocks (reverse priority):
1. Guild World Context (55) — dropped first
2. Character Memory (50)
3. User Memory (40)
4. Conversation History (30) — dropped last

This aligns with philosophy: **Conversation History** (most immediate context) should be preserved longest; **Guild World** (environmental, re-fetchable) is most expendable.

---

## 5. Modularity Verification

The philosophy requires: *"Context providers should define their own scope and boundaries, allowing future extensions without changing the architecture."*

| Provider | Defines Own Scope? | Hardcoded in PromptBuilder? | Hardcoded in Generation? |
|:---|:---|:---|:---|
| SystemContextProvider | ✅ (`persona_id` only) | ❌ | ❌ |
| PersonaContextProvider | ✅ (`persona_id` only) | ❌ | ❌ |
| CanonContextProvider | ✅ (planned, `persona_id` only) | ❌ | ❌ |
| ConversationHistoryProvider | ✅ (`guild_id, channel_id, user_id`) | ❌ | ❌ |
| UserMemoryProvider | ✅ (`guild_id, user_id`) | ❌ | ❌ |
| CharacterMemoryProvider | ✅ (planned, `guild_id, user_id, persona_id`) | ❌ | ❌ |
| GuildWorldContextProvider | ✅ (planned, `guild_id, channel_id`) | ❌ | ❌ |
| PersonaKnowledgeBaseProvider | ✅ (`persona_id` + query) | ❌ | ❌ |

**All providers self-declare scope via `PromptBuildContext` fields they consume.** PromptBuilder and Generation pipeline remain completely unaware of scoping rules.

---

## 6. Risk Assessment for Character Memory Implementation

| Risk | Likelihood | Impact | Mitigation |
|:---|:---|:---|:---|
| Character Memory accidentally leaks across guilds | Low | High | Scope key explicitly includes `guild_id`; unit tests for cross-guild isolation |
| Character Memory becomes a "second user memory" | Medium | High | ADR-0003 Boundaries are explicit; code review enforcement |
| Character Memory extraction pipeline reads PKB/Canon | Low | Medium | Extraction pipeline only consumes `ConversationManager` output |
| Channel-scoped vs Guild-scoped confusion in tests | Medium | Medium | Write tests for both scopes; document the guild-scoped decision |

---

## 7. Documentation Updates Required

1. **ADR-0003** — Update Section 3.6 (CharacterMemoryProvider) to remove `channel_id` from scope
2. **architecture.md** — Add "Multi-Guild Identity" section documenting the philosophy and scope matrix
3. **PromptBuildContext** — No changes needed (already has all required fields)

---

## 8. Acceptance Checklist for Next Phase

- [ ] ADR-0003 updated with corrected Character Memory scope (guild, not channel)
- [ ] Architecture.md updated with Multi-Guild Identity philosophy section
- [ ] Character Memory ADR created (separate ADR per implementation plan Step 3)
- [ ] Character Memory implementation follows guild-scoped design
- [ ] GuildWorldContextProvider implementation uses injected accessor protocol
- [ ] Cross-guild isolation tests added for all MUTABLE providers
- [ ] Token budget integration respects mutability drop order

---

## 9. Conclusion

The current architecture **strongly aligns** with the Multi-Guild Identity philosophy. The provider-based prompt assembly with explicit context scoping naturally enforces guild isolation without central coordination logic.

**One material change required**: Character Memory scope should be **per-guild** `(guild_id, user_id, persona_id)`, not per-channel. This aligns with the philosophy that "the character has one persistent identity, but participates in multiple independent communities" — and a relationship with a user persists across channels within a community.

Once ADR-0003 is updated, the architecture is ready for:
1. **Step 3**: Character Memory ADR + Implementation (guild-scoped)
2. **Step 4**: Canon Framework (global, immutable)
3. **Step 5**: GuildWorldContextProvider (environmental, request-scoped)

All implementations will remain modular, inspectable, and provider-agnostic per the established architecture.