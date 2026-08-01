# Architectural Audit Report — Freesona v1

This document follows ASD-STE100 Simplified Technical English.

**Date:** 2026-07-17  
**Scope:** Full codebase audit against `docs/architecture.md` and `AGENTS.md` principles  
**Status:** Baseline — no code changes made

---

## Executive Summary

This audit documents every architecture-level module in the Freesona codebase, measuring each against the project's stated principles: **provider independence**, **separation of concerns**, **modularity**, **explicit interfaces**, and **maintainability**.

The codebase is functional and well-structured for its current scope, but several architectural boundaries are blurred. The most significant gaps are:

1. **Prompt assembly is implicit and hardcoded** — no `PromptBuilder`, no inspectable context blocks
2. **Provider-specific logic leaks into shared generation pipeline** — Gemini `interaction_id` handling, NIM model params
3. **Discord UI lives in data-layer modules** — `utils/persona.py` contains modals and views
4. **Global mutable state** — module-level globals for persona, interaction IDs, rate limiting
5. **Config re-reads on hot paths** — `load_config()` called repeatedly in `generation.py`
6. **Character Memory does not exist** — documented as a separate system but unimplemented

---

## Module Inventory

| #  | Module                              | Layer   | File                   |
|----|-------------------------------------|---------|------------------------|
| 1  | Bot Entry & Lifecycle               | App     | `main.py`              |
| 2  | FastAPI Webhook Server              | Infra   | `fastapi_server.py`    |
| 3  | Config I/O                          | Infra   | `utils/config.py`      |
| 4  | Module Registry                     | Infra   | `utils/modules.py`     |
| 5  | Provider Abstraction                | Core    | `utils/providers.py`   |
| 6  | Generation Pipeline                 | Core    | `utils/generation.py`  |
| 7  | Persona Data Layer                  | Core    | `utils/persona.py`     |
| 8  | Long-Term Memory (User Facts)       | Core    | `utils/memory.py`      |
| 9  | Persona Knowledge Base (RAG)        | Core    | `utils/chroma.py`      |
| 10 | Autonomy Intent Evaluator           | Core    | `utils/intent.py`      |
| 11 | Security Guards                     | Core    | `utils/security.py`    |
| 12 | Role Resolution                     | Core    | `utils/roles.py`       |
| 13 | Web Search (Grounding)              | Core    | `utils/search.py`      |
| 14 | RSS/Atom Feed Parser                | Core    | `utils/rss.py`         |
| 15 | AI Cog (Discord Wiring)             | Discord | `cogs/ai/genai.py`     |
| 16 | Knowledge Base Cog (Discord Wiring) | Discord | `cogs/ai/chroma.py`    |
| 17 | Media Cogs (MVSEP, yt-dlp)          | Discord | `cogs/media/*.py`      |
| 18 | Moderation Cogs                     | Discord | `cogs/moderation/*.py` |
| 19 | System Cogs                         | Discord | `cogs/system/*.py`     |
| 20 | Tools Cogs                          | Discord | `cogs/tools/*.py`      |
| 21 | Fun Cogs                            | Discord | `cogs/fun/*.py`        |

---

## Detailed Module Audits

---

### 1. Bot Entry & Lifecycle (`main.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                             |
|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Bot instantiation, intent setup, extension loading, command sync, FastAPI server startup, prefix command, `on_ready`, error handlers                                                                                                                                   |
| **Inputs**                      | `BOT_TOKEN`, `CHANNEL_ID`, env vars, `config.json`                                                                                                                                                                                                                     |
| **Outputs**                     | Running Discord bot + FastAPI server (via `asyncio.gather`)                                                                                                                                                                                                            |
| **Dependencies**                | `discord.py`, `uvicorn`, `utils.config`, `utils.modules`, `fastapi_server`                                                                                                                                                                                             |
| **Architectural Boundary**      | **Composition root** — wires everything together. Should not contain business logic.                                                                                                                                                                                   |
| **Technical Debt**              | • `bot.config` caches config at startup but `utils.config.load_config()` re-reads disk on every command — stale cache risk\n• Legacy persona DM logic lives here (cross-cutting concern)\n• `on_command_error` / `on_app_command_error` duplicate error-handling logic |
| **Design Principle Violations** | • **Separation of Concerns**: Legacy persona migration notice is a UI concern in the entry point\n• **Single Responsibility**: `main.py` mixes startup, error handling, and persona migration UX                                                                       |
| **Recommended Action**          | • Move legacy persona DM to `GenAICog.cog_load()`\n• Centralize error handling in a shared utility\n• Remove `bot.config` cache or make `load_config()` the single source of truth                                                                                     |

---

### 2. FastAPI Webhook Server (`fastapi_server.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                  |
|---------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Health endpoints (`/`, `/health`), MVSEP webhook receiver (`/webhooks/mvsep`)                                                                                                                                                                                                               |
| **Inputs**                      | HTTP requests (MVSEP callbacks)                                                                                                                                                                                                                                                             |
| **Outputs**                     | JSON responses; resolves `asyncio.Future` for pending MVSEP jobs                                                                                                                                                                                                                            |
| **Dependencies**                | `fastapi`, `asyncio`, `cogs.media.mvsep` (via global `_mvsep_jobs`)                                                                                                                                                                                                                         |
| **Architectural Boundary**      | **Infrastructure adapter** — receives external callbacks, bridges to bot internals                                                                                                                                                                                                          |
| **Technical Debt**              | • Global `_mvsep_jobs: dict[str, asyncio.Future]` is shared mutable state across processes<br>• No authentication on webhook endpoint (relies on payload shape validation only)<br>• Tight coupling: `mvsep.py` imports `register_mvsep_job` / `unregister_mvsep_job` from `fastapi_server` |
| **Design Principle Violations** | • **Provider Independence**: MVSEP is a specific vendor; webhook handling should be behind an interface<br>• **Explicit Interfaces**: Global dict is an implicit contract                                                                                                                   |
| **Recommended Action**          | • Extract `WebhookReceiver` protocol; inject into MVSEP cog<br>• Add HMAC/signature validation for MVSEP callbacks<br>• Consider moving webhook registration to a dedicated service module                                                                                                  |

---

### 3. Config I/O (`utils/config.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                    |
|---------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Load/save `config.json`, provide defaults, merge env overrides, embed footer helper                                                                                                                                                                                                           |
| **Inputs**                      | `CONFIG_FILE_PATH` env var, `config.json` on disk                                                                                                                                                                                                                                             |
| **Outputs**                     | Merged config dict; `get_model_name()`, `get_provider_name()`, `get_provider_model()` accessors                                                                                                                                                                                               |
| **Dependencies**                | `os`, `json`, `dotenv`                                                                                                                                                                                                                                                                        |
| **Architectural Boundary**      | **Configuration singleton** — single source of truth for runtime settings                                                                                                                                                                                                                     |
| **Technical Debt**              | • `load_config()` reads disk **on every call** — called in hot paths (`generation.py` split functions, `providers.py`)<br>• `DEFAULT_CONFIG` mixes hardcoded defaults with `os.getenv()` — env vars evaluated at import time, not runtime<br>• No schema validation (Pydantic / `jsonschema`) |
| **Design Principle Violations** | • **Performance**: Repeated disk I/O on hot path<br>• **Explicit Interfaces**: Config shape is implicit dict                                                                                                                                                                                  |
| **Recommended Action**          | • Cache config in memory; invalidate on `/admin dumpconfig` or module reload<br>• Add Pydantic `Settings` model with validation<br>• Move env var reading into model defaults (evaluated at runtime)                                                                                          |

---

### 4. Module Registry (`utils/modules.py`)

| Aspect                          | Assessment                                                                                                                            |
|---------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Declares `CORE_EXTENSIONS` and `OPTIONAL_MODULES`; loads enabled modules from config                                                  |
| **Inputs**                      | `config.json["enabled_modules"]`                                                                                                      |
| **Outputs**                     | Dict of module name → enabled state; list of extensions to load                                                                       |
| **Dependencies**                | None (stdlib only)                                                                                                                    |
| **Architectural Boundary**      | **Plugin registry** — single source of truth for cog discovery                                                                        |
| **Technical Debt**              | • Dependency guard (`mvsep` requires `ytdlp`) enforced in admin cog, not here<br>• No versioning or compatibility metadata per module |
| **Design Principle Violations** | • **Separation of Concerns**: Dependency logic lives in admin cog, not registry                                                       |
| **Recommended Action**          | • Move dependency declarations into `OPTIONAL_MODULES` metadata<br>• Validate dependencies at load time in `load_enabled_modules()`   |

---

### 5. Provider Abstraction (`utils/providers.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|---------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Unified `generate_text()` across Gemini, OpenAI, Ollama, NIM, Azure, Groq, OpenRouter; message building; provider normalization                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **Inputs**                      | `user_prompt`, `system_prompt`, `provider`, `model`, `attachments`, `max_output_tokens`                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Outputs**                     | Generated text string                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Dependencies**                | `requests`, `google.genai`, `utils.config`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Architectural Boundary**      | **Provider adapter layer** — should isolate provider differences                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Technical Debt**              | • **Provider-specific logic leaks**: NIM has model-specific `extra_payload` (diffusiongemma, mistral-small-4); Gemini uses `genai.Client` directly with `system_instruction` config; others use OpenAI-compatible chat completions<br>• `build_messages()` assumes OpenAI-style multimodal format — not all providers support `image_url` with data URIs<br>• `normalize_provider_name()` has growing alias map — fragile<br>• No streaming support (only `generate_text` returns full string)<br>• No unified error taxonomy — callers catch `Exception` |
| **Design Principle Violations** | • **Provider Independence**: Caller must know provider name to pass correct model; model-specific params live here<br>• **Explicit Interfaces**: No `Provider` protocol/interface; `generate_text` is a monolithic function                                                                                                                                                                                                                                                                                                                               |
| **Recommended Action**          | • Define `Provider` protocol with `generate()`, `generate_stream()`, `supports_multimodal()`<br>• Move model-specific params to provider config (env or JSON)<br>• Implement adapter classes per provider; register in factory<br>• Return structured `GenerationResult` (text, usage, finish_reason, raw)                                                                                                                                                                                                                                                |

---

### 6. Generation Pipeline (`utils/generation.py`) — **Critical Path**

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Rate limiting, text splitting, attachment extraction, **prompt assembly**, KB retrieval, provider dispatch, response building, error handling, safety checks                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Inputs**                      | `prompt` (str                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |dict), `current_persona`, `persona_id`, `channel_id`, `guild_id`, `user_id`, `message_id`, `username`, `attachments`, `instruction_prefix`, `apply_persona` |
| **Outputs**                     | `ConversationResponse` (segments, reactions, gif)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Dependencies**                | `utils.memory`, `utils.chroma`, `utils.security`, `utils.config`, `utils.providers`, `discord`, `google.genai`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Architectural Boundary**      | **Generation orchestrator** — coordinates all context sources and provider call                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **Technical Debt**              | • **Monolithic function**: `generate()` is 80+ lines with 12 parameters<br>• **Hardcoded prompt ordering**: persona → memory → KB (lines 394–402) — not configurable, not inspectable<br>• **Provider leak**: `if provider_name != "gemini"` branch (line 412); Gemini uses Interactions API with `previous_interaction_id`; others use `generate_text()`<br>• **Global rate limiter**: `call_timestamps` list is module-global, not async-safe<br>• **Config re-reads**: `_get_split_min_length()` etc. call `load_config()` every invocation<br>• **Safety checks mixed in**: `detect_injection` / `sanitize_prompt` / `unsafe_output` called inline<br>• **No streaming**: `ConversationResponse` built after full generation |
| **Design Principle Violations** | • **Separation of Concerns**: Prompt assembly, provider dispatch, response formatting, rate limiting, safety — all in one function<br>• **Provider Independence**: Gemini-specific continuity logic in shared pipeline<br>• **Explicit Interfaces**: Prompt assembly is implicit string concatenation<br>• **Modularity**: Cannot test prompt assembly without provider call                                                                                                                                                                                                                                                                                                                                                     |
| **Recommended Action**          | **High Priority — Step 1 of Plan**<br>• Extract `PromptBuilder` with explicit context providers (System, Persona, Conversation, UserMemory, CharacterMemory, PersonaKB)<br>• Extract `ProviderDispatcher` implementing `Provider` protocol<br>• Extract `ResponseFormatter` (split, delay, build `ConversationResponse`)<br>• Extract `SafetyPipeline` (pre-check, sanitize, post-check)<br>• Make prompt ordering a declared `List[ContextProvider]`                                                                                                                                                                                                                                                                            |

---

### 7. Persona Data Layer (`utils/persona.py`) — **Critical Path**

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Persona JSON load/save, profile management, **assembly into system prompt**, Discord UI (modals, panels, buttons)                                                                                                                                                                                                                                                                                                                                                                                              |
| **Inputs**                      | `persona.json`, `personas.json`, Discord interactions                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Outputs**                     | Assembled persona string (`CURRENT_PERSONA`), saved JSON files                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Dependencies**                | `discord`, `discord.ui`, `json`, `os`, `dotenv`                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Architectural Boundary**      | **Persona data + UI** — currently conflated                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **Technical Debt**              | • **Module-level globals**: `PERSONA_DATA`, `CURRENT_PERSONA`, `CURRENT_PERSONA_ID`, `PERSONA_LOCKED`, `LEGACY_DETECTED` — mutable global state<br>• **UI in data layer**: `PersonaCoreModal`, `PersonaStyleModal`, `PersonaFullModal`, `PersonaPanelView` — Discord-specific UI code<br>• `init_persona()` runs on import — side effect at module load<br>• `assemble_persona()` uses hardcoded `ASSEMBLY_ORDER` and XML tags — not extensible<br>• No validation of persona fields (length, required fields) |
| **Design Principle Violations** | • **Separation of Concerns**: Data layer owns Discord UI<br>• **Explicit Interfaces**: Assembly order is a magic list; XML tags are magic strings<br>• **Testability**: Globals make unit testing require module reload                                                                                                                                                                                                                                                                                        |
| **Recommended Action**          | **High Priority — Step 3 of Plan**<br>• Split into `utils/persona_data.py` (load/save/assemble) and `cogs/ai/persona_ui.py` (modals/views)<br>• Replace globals with `PersonaState` class injected into cog<br>• Make `assemble_persona()` take explicit `AssemblyStrategy` (ordered list of `(field, tag)`)<br>• Add Pydantic model for persona schema with validation                                                                                                                                        |

---

### 8. Long-Term Memory — User Facts (`utils/memory.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                                                                                                                                  |
|---------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | SQLite fact extraction & storage (per guild/user), interaction ID store (in-memory), migration from JSON                                                                                                                                                                                                                                                                                                    |
| **Inputs**                      | User messages, `guild_id`, `user_id`, `message_id`, `channel_id`, provider client                                                                                                                                                                                                                                                                                                                           |
| **Outputs**                     | Stored facts; injected memory block string for prompt                                                                                                                                                                                                                                                                                                                                                       |
| **Dependencies**                | `aiosqlite`, `utils.providers.generate_text`, `datetime`, `json`, `re`                                                                                                                                                                                                                                                                                                                                      |
| **Architectural Boundary**      | **User fact store** — long-term, per-user, mutable                                                                                                                                                                                                                                                                                                                                                          |
| **Technical Debt**              | • **Two concerns in one module**: SQLite facts + in-memory `_interaction_store` (short-term provider continuity)<br>• `_interaction_store` is global dict — not persisted, not clustered<br>• `extract_and_store_fact()` calls provider directly — tight coupling to generation<br>• `FACT_EXTRACT_PROMPT` hardcoded string — not configurable<br>• Max 20 facts/user hardcoded (`MAX_FACTS_PER_USER = 20`) |
| **Design Principle Violations** | • **Separation of Concerns**: Short-term (continuity) and long-term (facts) are different systems<br>• **Provider Independence**: Fact extraction uses provider directly                                                                                                                                                                                                                                    |
| **Recommended Action**          | • Split into `utils/memory_facts.py` (SQLite) and `utils/continuity.py` (interaction IDs)<br>• Make fact extraction a `FactExtractor` protocol; inject provider<br>• Persist interaction IDs to SQLite for multi-instance support<br>• Make `MAX_FACTS_PER_USER` and importance threshold configurable                                                                                                      |

---

### 9. Persona Knowledge Base — RAG (`utils/chroma.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|---------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | ChromaDB client/collection management, ingestion pipeline (clean → speaker ID → chunk → metadata → embed), retrieval (`query_knowledge`), CRUD ops                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Inputs**                      | Raw source text, base metadata, query strings                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Outputs**                     | Ingestion-ready entries; formatted context strings for generation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Dependencies**                | `chromadb`, `pypdf`, `xml.etree`, `dotenv`, `uuid`, `re`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Architectural Boundary**      | **Canonical knowledge retrieval** — persona-agnostic, provider-independent                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **Technical Debt**              | • **Ingestion + Retrieval + Discord helpers in one file** — `parse_discord_chat_json`, `extract_text_from_bytes` are Discord/file-format specific<br>• `get_chroma_client()` global singleton — not injectable<br>• Metadata validation uses `frozenset` constants — good, but error messages are strings<br>• `ingest_source()` is deterministic but not easily testable end-to-end (requires Chroma)<br>• No re-ranking stage (architecture doc says optional — not implemented)<br>• `query_knowledge()` does metadata filtering via `where` clause — good |
| **Design Principle Violations** | • **Separation of Concerns**: File parsing (PDF, EPUB, Discord JSON) mixed with KB logic<br>• **Single Responsibility**: Ingestion pipeline stages not independently testable (though functions are separate)                                                                                                                                                                                                                                                                                                                                                 |
| **Recommended Action**          | • Move file parsers to `utils/ingestion/parsers.py`<br>• Extract `ChromaClientProvider` protocol for testing<br>• Add `retrieve_and_rerank()` placeholder for future re-ranking                                                                                                                                                                                                                                                                                                                                                                               |

---

### 10. Autonomy Intent Evaluator (`utils/intent.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                             |
|---------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Heuristic confidence scoring for autonomy trigger (mentions, attachments, code blocks, semantic triggers, question marks, filler penalties, monologue penalties)                                                                                                                                       |
| **Inputs**                      | `discord.Message`, `bot_user`, `has_channel_memory`                                                                                                                                                                                                                                                    |
| **Outputs**                     | `IntentResult(intent, confidence, requires_response, targets)`                                                                                                                                                                                                                                         |
| **Dependencies**                | `re`, `dataclasses`, `typing.TYPE_CHECKING`                                                                                                                                                                                                                                                            |
| **Architectural Boundary**      | **Pure decision logic** — no I/O, no side effects                                                                                                                                                                                                                                                      |
| **Technical Debt**              | • **Coupled to Discord types**: Takes `discord.Message` directly — hard to test with plain strings<br>• `INTENT_IMAGE_ANALYSIS` defined but never used as return value (only set internally)<br>• Thresholds hardcoded in `FREQUENCY_THRESHOLD` dict; config uses string keys (`low`/`default`/`high`) |
| **Design Principle Violations** | • **Testability**: Requires mock `discord.Message`                                                                                                                                                                                                                                                     |
| **Recommended Action**          | • Extract `MessageFeatures` dataclass (content, has_attachments, has_code_block, is_mention, is_reply, length, ends_with_question, is_filler, has_channel_memory)<br>• Make `evaluate_intent(features: MessageFeatures) -> IntentResult`<br>• Move thresholds to config                                |

---

### 11. Security Guards (`utils/security.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                                                                                                          |
|---------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | SSRF protection (`is_public_http_url`), prompt injection detection/sanitization (`detect_injection`, `sanitize_prompt`, `unsafe_output`), SymPy expression safety (`is_safe_expression`)                                                                                                                                                                                            |
| **Inputs**                      | URLs, prompt strings, model output text, math expressions                                                                                                                                                                                                                                                                                                                           |
| **Outputs**                     | Boolean checks, sanitized strings                                                                                                                                                                                                                                                                                                                                                   |
| **Dependencies**                | `ipaddress`, `re`, `socket`, `urllib.parse`, `ast`                                                                                                                                                                                                                                                                                                                                  |
| **Architectural Boundary**      | **Security library** — stateless, pure functions                                                                                                                                                                                                                                                                                                                                    |
| **Technical Debt**              | • `INJECTION_PATTERNS` and `OUTPUT_FLAGS` are hardcoded lists — not configurable<br>• IPv4 shorthand normalization is complex but incomplete (no IPv6 shorthand)<br>• `sanitize_prompt` uses `re.escape` on patterns — treats patterns as literal strings, not regex (may miss variants)<br>• `is_safe_expression` allowlist (`SAFE_FUNCTIONS`) not shown in audit (truncated file) |
| **Design Principle Violations** | None major — well-isolated                                                                                                                                                                                                                                                                                                                                                          |
| **Recommended Action**          | • Move patterns to config file (JSON/YAML) for updates without code change<br>• Add IPv6 shorthand handling<br>• Consider regex patterns with word boundaries for injection detection                                                                                                                                                                                               |

---

### 12. Role Resolution (`utils/roles.py`)

| Aspect                     | Assessment                                                                       |
|----------------------------|----------------------------------------------------------------------------------|
| **Responsibility**         | Classify message author as `model` / `user` / `bot` / `webhook`                  |
| **Inputs**                 | `discord.Message`, `bot_user_id`                                                 |
| **Outputs**                | Role string                                                                      |
| **Dependencies**           | `discord`                                                                        |
| **Architectural Boundary** | **Tiny utility** — pure function                                                 |
| **Technical Debt**         | None significant                                                                 |
| **Recommended Action**     | • Consider moving to `utils/discord_utils.py` if more Discord helpers accumulate |

---

### 13. Web Search / Grounding (`utils/search.py`)

| Aspect                          | Assessment                                                                                                                                                                                                 |
|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Gemini Grounding API calls with retry/fallback (primary → secondary model)                                                                                                                                 |
| **Inputs**                      | Query string                                                                                                                                                                                               |
| **Outputs**                     | `SearchResult(text, sources, failed, model_used)`                                                                                                                                                          |
| **Dependencies**                | `google.genai`, `asyncio`, `logging`                                                                                                                                                                       |
| **Architectural Boundary**      | **Search adapter** — Gemini-specific (uses Grounding API)                                                                                                                                                  |
| **Technical Debt**              | • **Provider-locked**: Only works with Gemini (uses `google.genai` Grounding API)<br>• No abstraction for other search providers (SerpAPI, Brave, etc.)<br>• `PRIMARY_MODEL` / `SECONDARY_MODEL` hardcoded |
| **Design Principle Violations** | • **Provider Independence**: Search is tied to Gemini                                                                                                                                                      |
| **Recommended Action**          | • Define `SearchProvider` protocol; implement `GeminiGroundingSearch`<br>• Allow fallback to generic search API via config                                                                                 |

---

### 14. RSS/Atom Feed Parser (`utils/rss.py`)

| Aspect                     | Assessment                                                                                                           |
|----------------------------|----------------------------------------------------------------------------------------------------------------------|
| **Responsibility**         | XML parsing, feed CRUD, seen-link deduplication                                                                      |
| **Inputs**                 | Feed URLs, `config.json` (`rss_feeds`, `rss_disabled`, `rss_seen`)                                                   |
| **Outputs**                | Parsed entries, updated `rss_seen` in config                                                                         |
| **Dependencies**           | `feedparser`, `utils.config`                                                                                         |
| **Architectural Boundary** | **Feed ingestion service**                                                                                           |
| **Technical Debt**         | • `rss_seen` capped at 500 in config — stored in JSON, not DB<br>• Direct `config` mutation in parser — side effects |
| **Recommended Action**     | • Move seen-links to SQLite<br>• Separate parsing from persistence                                                   |

---

### 15. AI Cog — Discord Wiring (`cogs/ai/genai.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|---------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | `on_message` pipeline (filters → route → debounce → generate → send), commands: `ask`, `write`, `search`, persona mgmt, memory mgmt, channel config, autonomy config, bot whitelist                                                                                                                                                                                                                                                                                           |
| **Inputs**                      | Discord messages, slash/prefix commands                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **Outputs**                     | Discord messages, embeds, config changes                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Dependencies**                | `utils.generation`, `utils.intent`, `utils.memory`, `utils.persona`, `utils.roles`, `utils.config`, `utils.modules`, `utils.search`, `discord.py`                                                                                                                                                                                                                                                                                                                             |
| **Architectural Boundary**      | **Discord adapter** — thin wiring over `utils/` logic                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Technical Debt**              | • **Fat cog**: 937 lines, 15+ commands, two message paths (conversation + autonomy)<br>• Imports module globals from `utils.persona` (`CURRENT_PERSONA`, `CURRENT_PERSONA_ID`, `LEGACY_DETECTED`, `PERSONA_LOCKED`)<br>• Debounce logic uses module-global `_pending_responses` dict<br>• Autonomy cooldowns use module-global dicts (`_autonomy_cooldown`, `_autonomy_user_cooldown`)<br>• `LAST_DEBUG` imported from `utils.config` — cross-module global for debug command |
| **Design Principle Violations** | • **Separation of Concerns**: Message routing, debounce, autonomy logic all in one cog<br>• **Global State**: Relies on module globals in `utils.persona`, `utils.config`                                                                                                                                                                                                                                                                                                     |
| **Recommended Action**          | • Extract `ConversationHandler` and `AutonomyHandler` classes<br>• Inject `PersonaState`, `ConfigProvider`, `GenerationService` instead of importing globals<br>• Move debounce/cooldown to dedicated `RateLimiter` service                                                                                                                                                                                                                                                   |

---

### 16. Knowledge Base Cog (`cogs/ai/chroma.py`)

| Aspect                          | Assessment                                                                                                                                                                                                                                                                   |
|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**              | Discord commands for KB: `kbadd` (modal), `kbsearch`, `kblist`, `kbdelete`, `kbpersona`                                                                                                                                                                                      |
| **Inputs**                      | Discord interactions, file attachments                                                                                                                                                                                                                                       |
| **Outputs**                     | KB entries, search results, lists                                                                                                                                                                                                                                            |
| **Dependencies**                | `utils.chroma`, `discord.ui`                                                                                                                                                                                                                                                 |
| **Architectural Boundary**      | **Discord adapter for KB**                                                                                                                                                                                                                                                   |
| **Technical Debt**              | • `MetadataModal` is 180+ lines — large modal with all metadata fields<br>• `kbadd` command does file extraction, then shows modal — two-step flow is fragile<br>• Validation logic duplicated in modal (`VALID_SOURCE_TYPES`, `VALID_ENTRY_TYPES`) — also in `utils.chroma` |
| **Design Principle Violations** | • **DRY**: Validation constants duplicated                                                                                                                                                                                                                                   |
| **Recommended Action**          | • Share validation constants from `utils.chroma` (already exported — use them)<br>• Extract `KBMetadataModal` to `cogs/ai/kb_ui.py`                                                                                                                                          |

---

### 17–21. Other Cogs (Media, Moderation, System, Tools, Fun)

| Aspect                     | Assessment                                                                                                                                                                                                          |
|----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Responsibility**         | Domain-specific Discord commands                                                                                                                                                                                    |
| **Architectural Boundary** | **Discord adapters** — each uses `utils/` for business logic                                                                                                                                                        |
| **Technical Debt**         | • `mvsep.py` calls `ytdlp.py` via `bot.get_cog("YtDlp")` — runtime cog lookup, not import (good)<br>• `math.py` has AST safety checker — well isolated<br>• `news.py` mutates `config.json` directly for `rss_seen` |
| **Recommended Action**     | • Generally well-scoped; no major architectural issues                                                                                                                                                              |

---

## Cross-Cutting Architectural Issues

### A. Prompt Assembly Is Implicit (Highest Priority)

**Current state** (`generation.py:394–402`):
```python
persona = current_persona if apply_persona else ""
if apply_persona and guild_id and user_id:
    memory_block = await inject_user_memory(guild_id, user_id, username)
    if memory_block:
        persona = f"{current_persona}\n\n{memory_block}"
if kb_context:
    persona = f"{persona}\n\n{kb_context}" if persona else kb_context
```

**Problems:**
- Ordering hardcoded: System → Persona → Memory → KB
- No way to inspect individual blocks before assembly
- No way to add/remove/reorder context providers without editing `generate()`
- Character Memory (planned) has no insertion point

**Required:** `PromptBuilder` with registered `ContextProvider` components (Step 1 of plan).

---

### B. Provider Independence Violations

| Location                | Issue                                                                                 |
|-------------------------|---------------------------------------------------------------------------------------|
| `generation.py:412`     | `if provider_name != "gemini"` branch                                                 |
| `generation.py:417–429` | Gemini Interactions API with `previous_interaction_id`                                |
| `providers.py:128–140`  | Gemini uses `genai.Client` + `system_instruction` config; others use chat completions |
| `providers.py:179–188`  | NIM model-specific `extra_payload`                                                    |
| `search.py`             | Only Gemini Grounding API                                                             |
| `memory.py:139–146`     | Fact extraction uses Gemini Interactions API directly                                 |

**Required:** `Provider` protocol with `generate()`, `generate_stream()`, `supports_continuity()`, `supports_multimodal()`.

---

### C. Global Mutable State

| Module             | Globals                                                                                      |
|--------------------|----------------------------------------------------------------------------------------------|
| `utils.persona`    | `PERSONA_DATA`, `CURRENT_PERSONA`, `CURRENT_PERSONA_ID`, `PERSONA_LOCKED`, `LEGACY_DETECTED` |
| `utils.memory`     | `_interaction_store`                                                                         |
| `utils.generation` | `call_timestamps`                                                                            |
| `utils.config`     | `LAST_DEBUG`                                                                                 |
| `cogs.ai.genai`    | `_pending_responses`, `_autonomy_cooldown`, `_autonomy_user_cooldown`                        |
| `fastapi_server`   | `_mvsep_jobs`                                                                                |

**Impact:** Untestable, not cluster-safe, hidden coupling.

**Required:** Replace with injected services / dependency injection.

---

### D. Config Hot-Path Re-reads

`utils.config.load_config()` called in:
- `generation.py:_get_split_min_length()` (every message split)
- `generation.py:_get_split_delay_base()` (every segment)
- `generation.py:_get_split_delay_per_char()` (every segment)
- `generation.py:_get_split_delay_max()` (every segment)
- `generation.py:_get_rate_limit()` (every generation)
- `providers.py:get_provider_model()` (every generation)

**Required:** In-memory config cache with invalidation on save.

---

### E. Character Memory — Missing System

Per `architecture.md` and issue description, **Character Memory** is a distinct system:
- **Responsibility**: Persistent shared history between persona and user (promises, shared experiences, recurring jokes, unfinished activities, relationship progression, persistent decisions)
- **Must NOT be**: User memory, canonical knowledge, conversation history, persona definition, prompt instructions
- **Mutability**: Mutable (unlike Persona KB which is immutable)

**Status:** Not implemented. No code, no schema, no ADR.

**Required:** ADR + implementation (Steps 2–4 of plan).

---

### F. Discord UI in Data Layer

`utils/persona.py` contains:
- `PersonaCoreModal`, `PersonaStyleModal`, `PersonaFullModal` (3 modals)
- `PersonaPanelView` (view with 4 buttons)
- `open_persona_panel()` (command handler)

`utils/chroma.py` has no UI (good), but `cogs.ai.chroma.py` has `MetadataModal` (180 lines).

**Required:** Move all Discord UI to `cogs/ai/` or `cogs/system/`.

---

## Compliance Matrix: AGENTS.md Principles

| Principle                 | Status      | Notes                                                          |
|---------------------------|-------------|----------------------------------------------------------------|
| Architecture First        | ⚠️ Partial  | Architecture doc exists but implementation has drifted         |
| Provider Independence     | ❌ Violated  | Multiple provider checks in shared code                        |
| Separation of Concerns    | ❌ Violated  | UI in data layer; generation pipeline monolith                 |
| Backwards Compatibility   | ✅ OK        | No breaking changes observed                                   |
| Code Style (Readability)  | ✅ Good      | Clear naming, consistent formatting                            |
| Type Hints                | ⚠️ Partial  | Present in new code; missing in older modules                  |
| Error Handling            | ⚠️ Partial  | Broad `except Exception` in several places                     |
| Logging                   | ✅ Good      | Uses `logging` module consistently                             |
| Documentation             | ✅ Good      | `architecture.md` is comprehensive                             |
| Configuration             | ⚠️ Partial  | No schema validation; hot-path re-reads                        |
| Memory Systems Separation | ❌ Violated  | Short-term + long-term in one module; Character Memory missing |
| Performance               | ⚠️ Deferred | Config I/O on hot path; no pooling                             |
| Security                  | ✅ Good      | SSRF, injection, AST guards present                            |
| Dependencies              | ✅ Minimal   | Well-justified deps                                            |
| Testing                   | ❌ Missing   | No test directory found in audit scope                         |

---

## Recommended Action Plan (Aligned with Issue Steps)

| Step | Action                                                                                   | Target Modules                                                                   | Priority    |
|------|------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|-------------|
| 0    | **This audit** — complete                                                                | —                                                                                | ✅ Done      |
| 1    | **PromptBuilder** — extract context providers, make ordering explicit, add debugging     | `utils/generation.py` → new `utils/prompt_builder.py`                            | 🔴 Critical |
| 2    | **Character Memory ADR** — define responsibility, schema, boundaries                     | New `docs/adr/character-memory.md`                                               | 🔴 Critical |
| 3    | **Character Memory Implementation** — SQLite store, retrieval, injection                 | New `utils/character_memory.py`                                                  | 🔴 Critical |
| 4    | **Integrate Character Memory into PromptBuilder**                                        | `utils/prompt_builder.py`                                                        | 🔴 Critical |
| 5    | **Provider Protocol** — define `Provider` interface, adapter classes                     | `utils/providers.py` → `utils/providers/*.py`                                    | 🟡 High     |
| 6    | **Persona/UI Separation** — move modals/views to cog                                     | `utils/persona.py` → `cogs/ai/persona_ui.py`                                     | 🟡 High     |
| 7    | **Config Cache** — in-memory cache with invalidation                                     | `utils/config.py`                                                                | 🟡 High     |
| 8    | **Global State Elimination** — inject `PersonaState`, `ContinuityStore`, `RateLimiter`   | `utils/persona.py`, `utils/memory.py`, `utils/generation.py`, `cogs/ai/genai.py` | 🟡 High     |
| 9    | **Memory Split** — separate facts vs. continuity                                         | `utils/memory.py` → `utils/memory_facts.py` + `utils/continuity.py`              | 🟢 Medium   |
| 10   | **Search Abstraction** — `SearchProvider` protocol                                       | `utils/search.py`                                                                | 🟢 Medium   |
| 11   | **Documentation Sync** — update `architecture.md` with new modules                       | `docs/architecture.md`                                                           | 🟢 Medium   |
| 12   | **Regression Testing** — add tests for PromptBuilder, CharacterMemory, Provider adapters | `tests/`                                                                         | 🟢 Medium   |

---

## Discrepancies: Implementation vs. `architecture.md`

| Doc Claim                                                                                                                      | Implementation Reality                                                                                                     |
|--------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| "Conversation history is managed server-side by Gemini's Interactions API"                                                     | True for Gemini; other providers are stateless — but this logic lives in `generation.py`, not a separate continuity module |
| "The bot stores continuity per `(guild_id, channel_id, user_id)`"                                                              | True — in `_interaction_store` global dict (in-memory, not persisted)                                                      |
| "Persona Knowledge Base supplies canonical knowledge… does not manage conversation state, user memory, or prompt construction" | ✅ Correct — `utils/chroma.py` is well-bounded                                                                              |
| "Provider implementations should remain stateless"                                                                             | ❌ `generation.py` stores Gemini `interaction_id` per user                                                                  |
| "Business logic should never be tightly coupled to Discord-specific code"                                                      | ❌ `utils/persona.py` contains Discord modals/views                                                                         |
| "Each module should have one primary responsibility"                                                                           | ❌ `utils/generation.py` has 6+ responsibilities                                                                            |
| "Avoid `if provider == 'gemini'` inside shared application logic"                                                              | ❌ Present in `generation.py` and `memory.py`                                                                               |

---

## Risk Assessment

| Risk                                                       | Likelihood | Impact | Mitigation                                       |
|------------------------------------------------------------|------------|--------|--------------------------------------------------|
| Prompt ordering changes break persona behavior             | High       | High   | PromptBuilder with explicit ordering + tests     |
| Provider switch breaks continuity                          | Medium     | High   | Provider protocol with `supports_continuity()`   |
| Config corruption crashes bot                              | Low        | High   | Pydantic validation + cache                      |
| Global state causes race conditions in scaled deployment   | Medium     | High   | Eliminate globals; use DI                        |
| Character Memory overlaps with User Memory / KB            | Medium     | Medium | ADR with strict boundaries before implementation |
| Knowledge base ingestion pipeline breaks on Chroma upgrade | Low        | Medium | Schema versioning already in place               |

---

## Conclusion

The Freesona codebase is **architecturally coherent at the module level** but **violates its own principles at the integration layer**. The generation pipeline (`utils/generation.py`) is the central nexus where provider independence, separation of concerns, and explicit interfaces break down.

**The audit confirms the issue's revised implementation order is correct:**
1. **Architecture Audit** (this document) — baseline established
2. **PromptBuilder** — fixes the core integration point
3. **Character Memory ADR + Implementation** — adds missing memory system with clear boundaries
4. **Persona/UI Separation** — cleans up the most visible layering violation
5. **Provider Protocol + Config Cache + Global State Elimination** — hardens the foundation

No code changes have been made. This report serves as the baseline for measuring refactoring progress.

---

*End of Report*