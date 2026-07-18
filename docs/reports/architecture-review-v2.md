# Architectural Review Report — Post ConversationManager Implementation

**Date**: 2026-07-17  
**Status**: Post-Step 1 (PromptBuilder) + Step 2 (ConversationManager) Implementation  
**Baseline**: `docs/reports/architecture-audit-v1.md`

---

## Executive Summary

The implementation of **PromptBuilder** (Step 1) and **ConversationManager** (Step 2) has successfully removed provider-owned conversation state from the architecture. All providers are now stateless and receive identical context through the system prompt.

However, several **legacy artifacts remain** that create architectural drift:

- `interaction_id` field persists in `PromptBuildContext` (unused)
- `memory.py` retains `_interaction_store` and associated functions (legacy Gemini Interactions API)
- `/clearmemory` command in `genai.py` still calls legacy `clear_interaction_id`
- `ConversationHistoryProvider` has a fallback bug (`channel_id or guild_id`)
- No tests exist for `conversation.py`

These must be resolved before Character Memory (Step 3) to prevent compounding technical debt.

---

## 1. Architecture Documentation Update Required

### Current State (architecture.md — *outdated*)

> **Short-term (provider continuity, in-session)**
>
> Conversation history is managed **server-side** by Gemini's Interactions API via `previous_interaction_id` when the active provider supports it. The bot stores continuity per `(guild_id, channel_id, user_id)` rather than one global ID per channel, which keeps user-specific threads isolated. Non-Gemini providers do not assume this continuity path. Cleared via `/clearmemory` or on restart.

### Required Rewrite

> **Short-term Memory (ConversationManager)**
>
> Freesona owns conversation history through `utils/conversation.py` — the **ConversationManager**. This subsystem:
>
> - Stores recent messages per `(guild_id, channel_id, user_id)` scope
> - Enforces configurable limits: `conversation_max_messages` (default 20), `conversation_token_budget` (default 4000), `conversation_ttl_seconds` (default 3600)
> - Provides `build_conversation_context()` for prompt injection (summary + recent messages format)
> - Runs periodic cleanup of expired conversations
>
> **Provider-owned continuity has been removed.** All providers (Gemini, OpenAI, Ollama, NIM, Azure, Groq, OpenRouter) are now **stateless** and receive identical conversation context via the system prompt through `ConversationHistoryProvider` (priority 30).
>

## 2. ConversationManager Architectural Review

### ✅ Responsibilities Confirmed (Single Responsibility)

| Responsibility                  | Implementation                                                          | Status |
|:--------------------------------|:------------------------------------------------------------------------|:-------|
| Storing conversation state      | `ConversationState` with `deque[ConversationMessage]`                   | ✅      |
| Pruning conversation history    | `_enforce_limits()` — message count + token budget                      | ✅      |
| Enforcing token/message budgets | Config-driven: `conversation_max_messages`, `conversation_token_budget` | ✅      |
| Exposing conversation context   | `build_conversation_context()` returns formatted string                 | ✅      |
| Expiration/cleanup              | `cleanup_expired_conversations()` + periodic task                       | ✅      |

### ❌ Responsibility Violations Found

| Violation                                         | Location                                                                                                                     | Severity                                                                                                                                                                                                                     |
|:--------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Auto-summarization placeholder**                | `_maybe_summarize()` at line 243-252                                                                                         | **Medium** — Contains comment "Summarization would require an LLM call" but returns `pass`. This is a **future feature leak**; summarization belongs in a separate `ConversationSummarizer` module, not ConversationManager. |
| **channel_id fallback bug**                       | `ConversationHistoryProvider.build()` line 172: `channel_id = getattr(context, "channel_id", None) or context.guild_id`      | **High** — Falls back to `guild_id` when `channel_id` is missing. This silently corrupts conversation scope (guild != channel). Should require `channel_id` or return empty.                                                 |
| **No `channel_id` in PromptBuildContext default** | `PromptBuildContext` has `channel_id: Optional[int] = None` but generation.py passes it. The fallback masks missing context. | **Medium**                                                                                                                                                                                                                   |

### ⚠️ Design Concerns

1. **Token estimation is rough** (`chars // 4`) — acceptable for budget enforcement but not for precise accounting. Document as approximation.
2. **Summary field exists but unused** — `ConversationState.summary` is never populated. Either implement summarization as separate subsystem or remove the field.
3. **Global in-memory store** — `_conversation_store` is process-local. Not suitable for multi-instance deployments. Document as known limitation.
4. **No persistence** — Conversations lost on restart. This matches previous behavior (Gemini interaction IDs also lost) but should be explicit.

---

## 3. PromptBuilder Audit

### Provider Independence Verification

| Provider                     | Knows About Other Providers? | Communicates With Others? | Only Produces Own Context? |
|:-----------------------------|:----------------------------:|:-------------------------:|:--------------------------:|
| SystemContextProvider        |              ❌               |             ❌             |             ✅              |
| PersonaContextProvider       |              ❌               |             ❌             |             ✅              |
| ConversationHistoryProvider  |              ❌               |             ❌             |             ✅              |
| UserMemoryProvider           |              ❌               |             ❌             |             ✅              |
| CharacterMemoryProvider      |              ❌               |             ❌             |      ✅ (placeholder)       |
| PersonaKnowledgeBaseProvider |              ❌               |             ❌             |             ✅              |

**All providers are independent.** ✅

### Ordering Declaration — Single Source of Truth

`_get_default_providers()` in `prompt_builder.py` (lines 146-166) is the **only** place provider order is declared:

```python
DEFAULT_PROVIDERS = [
    SystemContextProvider(),           # 10
    PersonaContextProvider(),          # 20
    ConversationHistoryProvider(),     # 30
    UserMemoryProvider(),              # 40
    CharacterMemoryProvider(),         # 50
    PersonaKnowledgeBaseProvider(),    # 60
]
```

**No hardcoded ordering elsewhere.** ✅

### Framework-Agnostic Verification

- No `discord` imports in `prompt_builder.py` or `prompt_builder_providers.py`
- No provider-specific logic (Gemini/OpenAI/etc.) in any provider
- `PromptBuildContext` contains only primitive types and `dict`

**Framework-agnostic.** ✅

### Residual Legacy Artifact

**`PromptBuildContext.interaction_id` (line 128)** — Still exists but **unused** by any provider. Remnant of Gemini Interactions API. Should be removed.

---

## 4. Generation Pipeline Review

### Current Responsibilities (generation.py: `generate()`)

| Responsibility                             | Location                                      | Architectural Owner                              |
|:-------------------------------------------|:----------------------------------------------|:-------------------------------------------------|
| Rate limiting                              | `rate_limit()`                                | ✅ Generation                                     |
| Input sanitization                         | `sanitize_prompt()`                           | ✅ Generation (security)                          |
| **Add user message to conversation**       | `add_user_message()`                          | ⚠️ **ConversationManager** (delegated correctly) |
| Build system prompt                        | `build_system_prompt()` → PromptBuilder       | ✅ Delegated                                      |
| Build input payload                        | `_build_input()`                              | ✅ Generation (provider messaging format)         |
| Select provider/model                      | `get_provider_name()`, `get_provider_model()` | ✅ Generation (config)                            |
| Call provider                              | `generate_text()`                             | ✅ Generation (orchestration)                     |
| **Add assistant response to conversation** | `add_assistant_message()`                     | ⚠️ **ConversationManager** (delegated correctly) |
| Error handling/classification              | `_classify_error()`                           | ✅ Generation                                     |
| Response cleaning                          | `clean_text()`                                | ✅ Generation                                     |

### Responsibility Leaks Found

| Leak                                                         | Location              | Assessment                                                                                                                                   |
|:-------------------------------------------------------------|:----------------------|:---------------------------------------------------------------------------------------------------------------------------------------------|
| `_build_input()` constructs provider-specific message format | generation.py:254-281 | **Acceptable** — This is the *provider messaging format* layer, not conversation logic. Belongs in `providers.py::build_messages()` instead. |
| `instruction_prefix` handling                                | generation.py:267-268 | **Acceptable** — Part of user message formatting.                                                                                            |
| Attachment multimodal encoding                               | generation.py:273-276 | **Should move to `providers.py`** — Provider-specific encoding (base64, mime types) belongs in provider adapter.                             |

**Recommendation**: Move `_build_input()` logic to `providers.py::build_messages()` where the OpenAI-format message construction already lives. This keeps generation.py purely as orchestration.

---

## 5. Provider Independence Verification

### Provider Interface Uniformity

All providers now implement the same interface via `generate_text()` in `providers.py`:

```python
def generate_text(
    user_prompt: str,
    *,
    system_prompt: str = "",
    provider: str | None = None,
    model: str | None = None,
    max_output_tokens: int = 1024,
    attachments: list[tuple[bytes, str]] | None = None,
) -> str:
```

### Provider-Specific Behavior Remaining

| Provider                                    | Special Handling                                                                            | Assessment                                                                               |
|:--------------------------------------------|:--------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------|
| **Gemini**                                  | Uses `genai.Client.models.generate_content` with `system_instruction` config                | ✅ Standard — uses system prompt from Freesona                                            |
| **OpenAI/Ollama/NIM/Azure/Groq/OpenRouter** | Use `post_chat_completion` with `build_messages()`                                          | ✅ Uniform                                                                                |
| **NIM (model-specific)**                    | `diffusiongemma` → token bump + sampler params; `mistral-small-4` → `reasoning_effort=none` | ⚠️ **Model-specific, not provider-specific**. Acceptable but document in `providers.py`. |
| **OpenRouter**                              | Adds `HTTP-Referer`, `X-Title` headers                                                      | ✅ Standard OpenRouter requirement                                                        |

### Legacy Conversation Handling — **REMOVED**

| Previously                                | Now                                    |
|:------------------------------------------|:---------------------------------------|
| `client.interactions.create()` for Gemini | Removed from `generation.py`           |
| `interaction_id` storage in `memory.py`   | Deprecated (still present, unused)     |
| Provider-specific continuity logic        | None — all use system prompt injection |

**All providers are stateless.** ✅

---

## 6. Character Memory Integration Readiness

### Current State

- `CharacterMemoryProvider` exists as **placeholder** (priority 50, `MUTABLE`, returns empty)
- `PromptBuildContext` has no character-memory-specific fields
- No storage, extraction, or retrieval logic exists

### Required Interfaces (Per ADR Requirements)

| Component      | Required Interface                                                                             |
|:---------------|:-----------------------------------------------------------------------------------------------|
| **Storage**    | `CharacterMemoryStore` — per `(guild_id, channel_id, user_id, persona_id)` scope               |
| **Extraction** | `extract_character_memories(conversation_history, persona_definition) → list[CharacterMemory]` |
| **Retrieval**  | `get_character_memory_context(guild_id, channel_id, user_id, persona_id) → str`                |
| **Pruning**    | Budget enforcement (token/message limits), TTL, importance scoring                             |
| **Mutability** | Explicit `add`, `update`, `delete` operations (unlike immutable PKB)                           |

### Relationship Boundaries (Must Enforce)

| System                  | Relationship                                                                                           | Enforcement                                                            |
|:------------------------|:-------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------|
| **ConversationManager** | **Source** — Character Memory *consumes* conversation history                                          | Character Memory reads from ConversationManager; never writes to it    |
| **User Memory**         | **Separate** — User Memory = facts *about* user; Character Memory = shared *experiences with* persona  | Different storage, different scope, different mutability               |
| **Persona KB**          | **Separate** — PKB = canonical facts *about* persona; Character Memory = shared *history with* persona | PKB immutable, Character Memory mutable; different priority (60 vs 50) |
| **PromptBuilder**       | **Consumer** — CharacterMemoryProvider reads from CharacterMemoryStore                                 | Provider pattern maintains independence                                |

### Risk Before Implementation

1. **No extraction pipeline** — Requires LLM call to distill conversations into memories. Must be async, batched, fault-tolerant.
2. **Scope definition critical** — `(guild, channel, user, persona)` quadruple key. Must handle persona switches correctly.
3. **Budget interaction** — Character Memory at priority 50 sits between User Memory (40) and PKB (60). Token budget must account for all three.
4. **No tests exist for conversation.py** — Character Memory will depend on ConversationManager; need conversation tests first.

---

## 7. Technical Debt Inventory

### Critical (Block Character Memory)

| Item                                                  | Location                          | Action                                    |
|:------------------------------------------------------|:----------------------------------|:------------------------------------------|
| `interaction_id` in `PromptBuildContext`              | `prompt_builder.py:128`           | Remove                                    |
| `_interaction_store` + `get/set/clear_interaction_id` | `memory.py:38-63`                 | Deprecate → Remove                        |
| `clear_interaction_id` called by `/clearmemory`       | `genai.py:644`                    | Migrate to `clear_conversation()`         |
| `channel_id` fallback bug                             | `prompt_builder_providers.py:172` | Fix: require `channel_id` or return empty |

### High

| Item                                 | Location                | Action                                   |
|:-------------------------------------|:------------------------|:-----------------------------------------|
| No tests for `conversation.py`       | —                       | Create `tests/test_conversation.py`      |
| `_build_input()` in generation.py    | `generation.py:254`     | Move to `providers.py::build_messages()` |
| Attachment encoding in generation.py | `generation.py:273-276` | Move to `providers.py`                   |
| `ConversationState.summary` unused   | `conversation.py:30`    | Remove or implement summarizer           |

### Medium

| Item                                      | Location               | Action                                        |
|:------------------------------------------|:-----------------------|:----------------------------------------------|
| Rough token estimation (`// 4`)           | `conversation.py:219`  | Document as approximation                     |
| Global in-memory store                    | `conversation.py:53`   | Document single-instance limitation           |
| NIM model-specific params in providers.py | `providers.py:178-188` | Document as model-level, not provider-level   |
| `_maybe_summarize()` placeholder          | `conversation.py:243`  | Remove or extract to `ConversationSummarizer` |

---

## 8. Documentation Updates Required

| Document                                | Section             | Required Change                                        |
|:----------------------------------------|:--------------------|:-------------------------------------------------------|
| `architecture.md`                       | Short-term Memory   | **Full rewrite** (see Section 1)                       |
| `architecture.md`                       | Memory System       | Add ConversationManager as canonical short-term memory |
| `architecture.md`                       | Module System       | Note `utils/conversation.py` as new module             |
| `config.sample.json`                    | Conversation config | Already added (✅)                                      |
| `docs/reports/architecture-audit-v1.md` | —                   | Superseded by this report                              |
| `AGENTS.md`                             | —                   | No change needed (principles still valid)              |

---

## 9. Acceptance Checklist for Character Memory (Step 3)

Before implementing Character Memory, the following must be **done**:

- [ ] Remove `interaction_id` from `PromptBuildContext`
- [ ] Remove `_interaction_store` and associated functions from `memory.py`
- [ ] Update `/clearmemory` to use `clear_conversation()`
- [ ] Fix `ConversationHistoryProvider.channel_id` fallback bug
- [ ] Create `tests/test_conversation.py` with coverage for:
  - Message add/retrieve
  - Budget enforcement (message count, token budget)
  - TTL cleanup
  - `build_conversation_context()` formatting
  - `clear_conversation()` per-user and per-channel
- [ ] Move `_build_input()` logic to `providers.py::build_messages()`
- [ ] Move attachment encoding to `providers.py`
- [ ] Remove `ConversationState.summary` field or implement `ConversationSummarizer`
- [ ] Update `architecture.md` Short-term Memory section

---

## 10. Recommendation: Next Architectural Milestone

**Do not implement Character Memory yet.**

Complete the **Cleanup Sprint** (items in Section 9) first. This will:

1. Eliminate all legacy Gemini Interactions API artifacts
2. Establish ConversationManager as tested, reliable foundation
3. Clean provider interface boundaries
4. Prevent Character Memory from inheriting technical debt

**Estimated effort**: 2-3 focused sessions.

Then proceed to **Character Memory ADR + Implementation** with a clean base.

---

## Appendix: Module Responsibility Map (Current)

| Module                              | Responsibility                                                         | Depends On                                                                                    |
|:------------------------------------|:-----------------------------------------------------------------------|:----------------------------------------------------------------------------------------------|
| `utils/conversation.py`             | Short-term conversation state, budgets, context formatting             | `utils/config.py`                                                                             |
| `utils/prompt_builder.py`           | Prompt assembly orchestration, provider registry                       | `utils/prompt_builder_providers.py`                                                           |
| `utils/prompt_builder_providers.py` | Individual context contributions (6 providers)                         | `utils/conversation.py`, `utils/memory.py`, `utils/chroma.py`, `utils/persona.py`             |
| `utils/generation.py`               | Orchestration: sanitize → prompt → provider → store → respond          | `utils/prompt_builder.py`, `utils/conversation.py`, `utils/providers.py`, `utils/security.py` |
| `utils/providers.py`                | Provider adapter implementations, message formatting                   | `utils/config.py`                                                                             |
| `utils/memory.py`                   | Long-term user facts (SQLite), **legacy interaction IDs (deprecated)** | `aiosqlite`                                                                                   |
| `utils/chroma.py`                   | Persona Knowledge Base (RAG)                                           | `chromadb`                                                                                    |
| `utils/persona.py`                  | Persona data layer, assembly                                           | —                                                                                             |
| `cogs/ai/genai.py`                  | Discord command layer, autonomy, memory management UI                  | `utils/*`                                                                                     |

---

*Report generated per architectural review requirements. All findings traceable to source lines.*
