# Features

## PromptBuilder Architecture

Freesona assembles prompts using a modular **PromptBuilder** system with independent **ContextProvider** components. Each provider contributes a single, well-defined context block without knowledge of the others. Provider ordering is declared in a single registry (`utils/prompt_builder.py`) and can be inspected at runtime via `inspect()`.

**Provider Priority Order:**

| Priority | Provider               | Mutability | Description                                                                                  |
|:---------|:-----------------------|:-----------|:---------------------------------------------------------------------------------------------|
| 10       | System                 | IMMUTABLE  | Model behavior constraints, safety, format                                                   |
| 20       | Persona                | IMMUTABLE  | Structured persona fields (core, background, beliefs, style, instructions)                   |
| 25       | Canon                  | IMMUTABLE  | Modular canon blocks: identity, beliefs, motivations, rules, world assumptions, explanations |
| 30       | Conversation History   | MUTABLE    | Recent conversation context (summary + messages) from ConversationManager                    |
| 40       | User Memory            | MUTABLE    | Long-term facts about the user (extracted from conversation)                                 |
| 50       | Character Memory       | MUTABLE    | Shared experiences: promises, recurring jokes, relationship progression                      |
| 55       | Guild World            | MUTABLE    | Environmental context: server name, channel name, topic                                      |
| 60       | Persona Knowledge Base | IMMUTABLE  | Retrieved canonical knowledge from source material (RAG)                                     |

---

## Persona System

Freesona's persona is split into five structured fields edited through a button-based `/setpersona` panel — no restart required.



| Field                          | Edited via    |
|:-------------------------------|:--------------|
| Core Personality & Traits      | `/setpersona` |
| Background & History           | `/setpersona` |
| Beliefs, Likes & Dislikes      | `/setpersona` |
| Language & Communication Style | `/setpersona` |
| System Instructions            | `/setpersona` |

Changes take effect immediately. The assembled persona is injected as the system instruction on every generation call, assembled in XML-tagged blocks for clarity.

**Persona profiles** — save, load, list, and delete named presets with `/personasave`, `/personaload`, `/personalist`, `/personadelete`. Useful for switching between characters or server contexts.

**Persona lock** — `/personalock` prevents accidental overwrites. `/personaunlock` to re-enable editing.

**Legacy support** — if a `persona.txt` file exists and no `persona.json` is found, the bot falls back to it automatically. Existing installations don't break on upgrade.

**Debug** — `/debugpersona` shows the fully assembled persona, last prompt sent to the model, active provider and model, lock state, and autonomy status.

---

## Memory Systems

Freesona treats memory as three distinct, non-overlapping systems:

### Short-term Memory — ConversationManager (`utils/conversation.py`)

Freesona owns conversation history through the **ConversationManager** — a provider-agnostic short-term memory subsystem. All providers (Gemini, OpenAI, Ollama, NIM, Azure, Groq, OpenRouter) are **stateless** and receive identical conversation context via the system prompt.

**ConversationManager responsibilities:**

- Stores recent messages per `(guild_id, channel_id, user_id)` scope
- Enforces configurable limits:
  - `conversation_max_messages` (default: 20)
  - `conversation_token_budget` (default: 4000, rough estimation)
  - `conversation_ttl_seconds` (default: 3600 / 1 hour)
- Provides `build_conversation_context()` for prompt injection (summary + recent messages format)
- Runs periodic cleanup of expired conversations

**Provider-owned continuity has been removed.** The legacy Gemini Interactions API (`previous_interaction_id`) and `utils/memory.py::_interaction_store` are deprecated. The `/clearmemory` command now clears ConversationManager state via `clear_conversation()`.

Conversation history is injected into the system prompt through `ConversationHistoryProvider` (priority 30 in PromptBuilder), ensuring all providers receive the same context regardless of native capabilities.

### Character Memory (`utils/character_memory.py`)

Character Memory stores **persistent shared history** between the persona and the user within a guild:

- **Promises** — "We agreed to play chess next week"
- **Shared experiences** — "We decorated the server for Halloween"
- **Recurring jokes** — "The ongoing coffee gag"
- **Unfinished activities** — "We were planning a movie night"
- **Relationship progression** — "User helped the character through a difficult time"
- **Persistent decisions** — "Character agreed to join user's club"

**Scope:** Per `(guild_id, user_id, persona_id)` — relationships persist across channels within the same guild.

**Extraction pipeline:** Consumes ConversationManager history to extract new memories via LLM-based analysis, scored by importance (0.0–1.0). Memories below `character_memory_min_importance` (default: 0.3) are dropped. Budget enforced at `character_memory_max_memories` (default: 50) per scope.

**Boundaries:** Never stores canonical facts (Canon/PKB), user profile facts (User Memory), or conversation history (ConversationManager).

### Long-term Memory — User Facts (`utils/memory.py`)

After each user message, a background task runs fact extraction — asking the active model whether the message reveals anything worth remembering (name, job, location, interests, projects, relationships). Facts are scored by importance (0.0–1.0), deduplicated by message ID, and capped at 20 per user. Facts below 0.3 importance are dropped. The top facts are injected into the system prompt for future conversations with that user.

Stored in `memory.db`, keyed by `(guild_id, user_id)`. Survives restarts and is provider-neutral.

### User Distinction

Every message payload is tied to a stable Discord `user_id` before reaching the model. The bot uses that identity key to keep memory isolated per user, even in busy multi-user channels.

---

## Canon Framework (`utils/canon.py`)

The **Canon Framework** replaces the monolithic persona prompt with modular, immutable components that explain *why* a character behaves as they do, not merely *what* they do. It is the authoritative source of canonical truth alongside the PKB.

**Six component types:**
1. **Core Identity** — Who the character fundamentally is
2. **Core Beliefs** — What the character believes about the world
3. **Motivations** — What drives the character's actions
4. **Behavioral Rules** — Constraints the character follows (must include explanation)
5. **World Assumptions** — How the character perceives their world
6. **Canon Explanations** — The "why" behind behaviors, not just the "what"

**Features:**
- Authored, immutable components (never learned from conversation)
- Versioned snapshots for rollback
- Export/import for portability
- Canonical Truth Invariant validation (behavioral rules must have explanations; suspicious content flagged)
- Integrates as `CanonContextProvider` (priority 25, IMMUTABLE)

---

## Guild World Context (`utils/guild_world.py`)

The character exists *through* Discord, not inside a single guild. Guild World Context provides **environmental grounding** — the "where" of the current interaction — without storing it as memory.

**Supplies per request:**
- Guild (server) name
- Channel name
- Channel topic/description
- Approximate member count (population)

**Scope:** Per `(guild_id, channel_id)` — request-scoped, no persistence, no history, no cross-guild awareness.

The same persona naturally adapts its wording to different servers without changing who it is. Guilds represent different communities, not different characters.

---

## Persona Knowledge Base (RAG) (`utils/chroma.py`, `utils/generation.py`)

### Definition

**Persona Knowledge Base (PKB)** is the retrieval subsystem responsible for supplying canonical persona knowledge to the generation pipeline. It stores structured knowledge about a persona and provides relevant context during generation. It does not manage conversation state, user memory, or prompt construction.

### Purpose

The knowledge base stores **canonical, factual information** about a persona — dialogue, narration, events, relationships, and descriptions — sourced from original material (anime, novels, manga, games, etc.). It supplies canonical knowledge about a persona as one input to the generation pipeline and does not independently determine model behavior. It is **not** responsible for:
- Conversation history (handled by **ConversationManager** in `utils/conversation.py`)
- User long-term memory (handled by `utils/memory.py`)
- Persona definition/prompt engineering (handled by `utils/persona.py`)
- Safety instructions or model reasoning

### Architecture



```text
┌─────────────────────────────────────────────────────────────────┐
│                    Ingestion Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│  Raw Source ──► Cleaning ──► Speaker ID ──► Semantic Chunking  │
│       │                                                │        │
│       ▼                                                ▼        │
│  Metadata Assignment ──► Embedding ──► ChromaDB Storage        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Retrieval Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│  User Message ──► Embedding ──► Metadata Filtering ◄────────── │
│       │                  │           Vector Search              │
│       ▼                  ▼           ▼                           │
│  Top-k Results ◄─── Re-ranking (optional) ◄─────────────────── │
│       │                                                        │
│       ▼                                                        │
│  Context Assembly ──► Language Model (Persona + Memory + KB)   │
└─────────────────────────────────────────────────────────────────┘
```



Where supported by the vector database, metadata filtering occurs before or alongside vector search to reduce the candidate set. An optional re-ranking stage can be added later without changing the overall architecture.

### Knowledge Lifecycle

Embeddings, metadata schemas, and source material will inevitably change over the life of the project. The knowledge lifecycle acknowledges this:

```text
Source Material
      ↓
Cleaning
      ↓
Chunking
      ↓
Metadata Assignment
      ↓
Embedding
      ↓
Validation
      ↓
Serving
      ↓
Updates / Re-embedding
```

When embedding models change or metadata schemas evolve, entries can be re-ingested with updated `schema_version` and `embedding_model` fields. The deterministic ingestion pipeline makes this process reproducible.

### Data Model

Each knowledge entry represents **one semantic unit** (atomic chunk):



```json
{
  "id": "kb_abc123...",
  "document": "Canonical dialogue or descriptive passage.",
  "metadata": {
    "persona": "chisato_nishikigi",
    "source": "Episode 06",
    "source_type": "anime",
    "entry_type": "dialogue",
    "topics": ["friendship", "optimism"],
    "episode": "06",
    "chapter": "",
    "scene": "Aquarium",
    "speaker": "Chisato",
    "timestamp": "S01E06 12:34",
    "canon_level": "canon",
    "tags": "canon, emotional, key_moment",
    "schema_version": 1,
    "embedding_model": "text-embedding-3-large"
  }
}
```



#### Schema Versioning

Knowledge entries include version metadata so future migrations remain manageable:



| Field             | Description                                 |
|:------------------|:--------------------------------------------|
| `schema_version`  | Schema version of the entry (default: `1`)  |
| `embedding_model` | Embedding model used to generate the vector |



These fields are automatically populated during ingestion and should be treated as immutable for the lifetime of the entry.

#### Design Principle: Store Canonical Facts, Not Interpretations

Metadata should describe **objective facts** about the source material rather than inferred personality traits.

**Prefer:**

- `speaker` — Who is speaking
- `episode` / `chapter` — Structural location in the source
- `source_type` — Media format (anime, novel, manga, game, etc.)
- `scene` — Setting or location
- `topics` — Semantic subjects (e.g., `friendship`, `optimism`)
- `canon_level` — Canonical priority

**Avoid storing subjective interpretations such as:**

- `tone` — (e.g., "cheerful", "melancholic")
- `intent` — (e.g., "comforting", "manipulative")
- `emotional_state` — (e.g., "happy", "angry")

These inferences belong to the language model during generation. Storing them in the knowledge base would embed a single interpretation permanently, reducing flexibility across providers and prompting strategies.

#### Required Metadata Fields



| Field         | Description                                                                                 |
|:--------------|:--------------------------------------------------------------------------------------------|
| `persona`     | Persona identifier (e.g., `chisato_nishikigi`)                                              |
| `source`      | Original source reference (e.g., `Episode 06`, `Chapter 12`)                                |
| `source_type` | Media type: `anime`, `novel`, `manga`, `game`, `guidebook`, `interview`, `website`, `other` |
| `entry_type`  | Content type: `dialogue`, `narration`, `event`, `relationship`, `description`               |
| `topics`      | Semantic topics for retrieval (non-empty list)                                              |



#### Optional Metadata Fields



| Field         | Description                                                                  |
|:--------------|:-----------------------------------------------------------------------------|
| `episode`     | Episode number                                                               |
| `chapter`     | Chapter number                                                               |
| `scene`       | Scene description                                                            |
| `speaker`     | Speaking character (for dialogue)                                            |
| `timestamp`   | Source timestamp (e.g., `2023-01-15`, `S01E06 12:34`)                        |
| `canon_level` | Canon priority: `canon`, `semi-canon`, `non-canon`, `headcanon`, `alternate` |
| `tags`        | Additional indexing tags (comma-separated)                                   |



### Ingestion Pipeline

The ingestion pipeline (`utils/chroma.py`) provides utilities for deterministic, reproducible ingestion:

1. **`clean_source_text(text)`** — Normalizes line endings, removes excessive blank lines
2. **`identify_speakers(text, patterns?)`** — Extracts speaker-attributed dialogue lines
3. **`chunk_semantic_units(text, max_size, min_size, speaker_data?)`** — Splits text into atomic semantic chunks (one exchange, one event, one monologue)
4. **`assign_metadata(chunks, base_metadata)`** — Applies base metadata + chunk-specific fields (speaker → `entry_type: dialogue`)
5. **`ingest_source(raw_text, base_metadata, ...)`** — Full pipeline: clean → identify → chunk → assign metadata

Each stage is deterministic and can be tested independently.

### Canonical Truth Invariant

**Architectural Principle**: *No context provider may establish canonical truth about the character.*

Only two sources are authorized to define objective facts about the persona:

1. **Canon Framework** (`CanonContextProvider`, priority 25) — Authored, immutable canon blocks that give the reason for behavior: core identity, core beliefs, core motivations, behavioral rules, world assumptions, and canon explanations.
2. **Persona Knowledge Base** (`PersonaKnowledgeBaseProvider`, priority 60) — Retrieved canonical knowledge from source material (RAG), filtered by `persona_id`.

All other context providers are **strictly descriptive** and must never define what the character "is" or "believes" in a canonical sense:



| Provider                      | Authority               | What It May Describe                                                                                    |
|:------------------------------|:------------------------|:--------------------------------------------------------------------------------------------------------|
| `SystemContextProvider`       | Hard constraints        | Model behavior constraints (safety, format, reasoning)                                                  |
| `PersonaContextProvider`      | Identity expression     | Role, background, beliefs, language style (the *what*)                                                  |
| `ConversationHistoryProvider` | Session continuity      | *What was said* in this conversation                                                                    |
| `UserMemoryProvider`          | User facts              | *What the persona knows about the user* across sessions                                                 |
| `CharacterMemoryProvider`     | Relationship history    | *What they've experienced together*: promises, shared events, recurring jokes, relationship progression |
| `GuildWorldContextProvider`   | Environmental grounding | *Where they are*: server name, channel context, local norms                                             |



**Enforcement**:

- Canon and PKB are `IMMUTABLE` — they change only via explicit admin action (`/setpersona`, `/kbadd`, `/kbdelete`)
- All other providers are `MUTABLE` — they evolve through interaction
- Code review and tests must verify no `MUTABLE` provider writes canonical facts (e.g., "Chisato grew up in Osaka" must never appear in Character Memory)

This invariant prevents **canon drift** — the gradual corruption of character identity through accumulated conversation context. It ensures the character remains authentic to their source material while still forming genuine, contextual relationships.

### Retrieval & Context Construction

The retrieval function `retrieve_knowledge_context(query, persona, top_k)` in `utils/generation.py`:

1. Embeds the user's message
2. Queries ChromaDB with **metadata filtering (by `persona`) occurring before or alongside vector search** to reduce the candidate set
3. Returns the **most relevant k entries** (where `k` is configurable via `kb_top_k`, default 5)
4. An optional re-ranking stage can be added later without changing the overall architecture
5. Assembles context in the **Relevant Canonical Context** format:

```text
Relevant Canonical Context
1. Document text...
   (Source: Episode 06, Type: dialogue, Scene: Aquarium, Speaker: Chisato, Chapter: , Timestamp: S01E06 12:34, Canon: canon)
2. Document text...
   (Source: Chapter 12, Type: narration, Scene: , Speaker: , Chapter: Chapter 12, Timestamp: , Canon: canon)
```

This context is appended to the persona prompt **after** long-term memory, following the PromptBuilder priority order:

```text
System (10) → Persona (20) → Canon (25) → Conversation History (30) → User Memory (40) → Character Memory (50) → Guild World (55) → PKB (60) → Generation
```

### Discord Integration

- **`/kbadd`** — Modal UI (`MetadataModal` in `cogs/ai/chroma.py`) for adding entries with all required and optional metadata fields
- **`/kbsearch`** — Semantic search with optional persona filter
- **`/kblist`** — List recent entries
- **`/kbdelete`** — Delete entry by ID

### Provider Independence

The knowledge base:

- Does **not** depend on any specific AI provider (Gemini, OpenAI, Ollama, etc.)
- Does **not** use provider-native memory systems
- Stores embeddings in ChromaDB (local or remote)
- Provides identical retrieval behavior across all providers
- Is fully **persona-agnostic** — adding a new persona requires only source material + metadata, no code changes

### Configuration

Environment variables (see `.env.sample`):

- `CHROMA_COLLECTION` — Collection name (default: `freesona`)
- `CHROMA_PERSIST_DIRECTORY` — Storage path (default: `./.chroma`)

Config keys (see `config.sample.json`):

- `kb_enabled` — Enable/disable knowledge base retrieval (default: `true`)
- `kb_top_k` — Number of knowledge base entries to retrieve per query (default: `5`). Higher values provide more context to the model (better accuracy for complex questions) but increase token usage and latency. Lower values are faster but may miss relevant details. Typical range: 3–10.
- `kb_collection` — Override collection name
- `kb_persist_directory` — Override storage path

---

## Multi-Guild Identity Philosophy

Freesona models a character that exists **through** Discord, not inside a single guild.

- **Canon is global and immutable** — The character's identity, beliefs, and rules are the same everywhere
- **Persona is global** — The structured persona definition applies universally
- **PKB is global** — Canonical knowledge is shared across all guilds
- **Conversation History is local** — Per `(guild_id, channel_id, user_id)` scope
- **Character Memory is local to the guild** — Per `(guild_id, user_id, persona_id)` scope; relationships persist across channels within a guild
- **Guild World Context is environmental** — Request-scoped, no persistence

**The character must never automatically leak information between guilds.** A conversation, relationship, joke, promise, or shared event from Guild A should not appear in Guild B unless an explicit future feature is designed for that purpose.

This is like a real Discord user: they participate in many servers, naturally compartmentalize conversations, don't randomly tell one community about another, and their personality stays consistent while their social context changes.

---

## Multiple AI Providers

Freesona routes generation through a provider abstraction so the same commands can target different backends without changing command code. Supported providers:



| Provider         | Key env var                         |
|:-----------------|:------------------------------------|
| Gemini (default) | `GOOGLE_API_KEY`                    |
| OpenAI           | `OPENAI_API_KEY`                    |
| Ollama           | `OLLAMA_BASE_URL`                   |
| NVIDIA NIM       | `NVIDIA_API_KEY`                    |
| Azure AI Foundry | `AZURE_AI_KEY`, `AZURE_AI_BASE_URL` |
| Groq             | `GROQ_API_KEY`                      |
| OpenRouter       | `OPENROUTER_API_KEY`                |



Set `AI_PROVIDER` and `AI_PROVIDER_MODEL` in `.env`, then add the matching credentials. `/model set` and `/model reset` change the active model at runtime without a restart. The provider abstraction is shared across Gemini, OpenAI, Ollama, NVIDIA NIM, Azure AI Foundry, Groq, and OpenRouter; all providers are now stateless and receive conversation context via the system prompt.

---

## Autonomous Mode

When enabled, the bot can join an active conversation unprompted. It uses a confidence-scored intent evaluator (`utils/intent.py`) rather than a random dice roll:



| Signal                                           | Score |
|:-------------------------------------------------|:------|
| Direct mention or reply to bot                   | +0.90 |
| Attachment present                               | +0.50 |
| Code block present                               | +0.40 |
| Semantic trigger word (what, how, explain, fix…) | +0.40 |
| Ends with question mark                          | +0.20 |
| Channel has existing conversation memory         | +0.10 |
| Short filler message (lol, ok, emoji-only)       | −0.30 |
| Long monologue with no question and no mention   | −0.20 |



Frequency thresholds: `low` = 0.70, `default` = 0.50, `high` = 0.35. A 120-second per-channel cooldown prevents it from dominating a conversation. A separate 60-second per-user cooldown prevents repeated autonomous responses to the same user.

---

## Debounced Responses

A per-user-per-channel debounce waits before generating a reply. Rapid successive messages from the same user in the same channel — "wait" / "actually" / "never mind" — collapse into one prompt before the bot responds.

---

## Multimodal Input

Attach an image, PDF, audio file, video, or code file to any AI command or conversation message. The bot reads the attachment alongside the text prompt via the active provider's multimodal pipeline. Supported types include PNG, JPEG, WEBP, GIF, PDF, plain text, Markdown, CSV, MP3, WAV, MP4, and more. Non-Gemini providers receive text-only input; attachments are silently ignored on providers that don't support multimodal input.

---

## Web Search

`~search <query>` fetches results using Gemini grounding first. If grounding is unavailable, it falls back to legacy Google Custom Search. Requires `GOOGLE_API_KEY`; `GOOGLE_SEARCH_API_KEY` and `SEARCH_ENGINE_ID` are optional for the fallback path.

---

## RSS News Feeds

`/rss latest <feed>` reads RSS/Atom feeds and posts the latest headlines. `/rss add`, `/rss remove`, and `/rss list` manage feed sources. Default feeds include BBC World, BBC Tech, NPR News, and Al Jazeera. Auto-posting polls every 5 minutes and sends new articles to the configured channel. Source logos are fetched via LogoKit if `LOGOKIT_TOKEN` is set.

---

## Audio Separation

`~separate` isolates vocals and instrumental from any audio using MVSEP's BS Roformer model (SDR vocals: 11.89, SDR instrum: 18.20). Accepts a file attachment, a direct audio URL, or any platform URL supported by yt-dlp. Output links are labeled as Vocals/Instrumental where MVSEP metadata allows it. Links are hosted by MVSEP and expire after some time. Free tier allows one job at a time. Webhook-based completion is supported when `MVSEP_WEBHOOK_URL` is configured; falls back to polling every 10 seconds otherwise. Requires `MVSEP_API_KEY`.

---

## Media Downloader

`~download <url>` downloads video at the best available resolution (1080p → 720p → 480p → compressed) and sends it directly in chat. `~audio <url>` extracts audio as MP3. Both use yt-dlp and ffmpeg. File size limit: 10 MB (Discord's free upload limit). Audio stream integrity is verified after every merge — silent merge failures that produce video-only files are caught and retried at a lower resolution. Per-user cooldown: 30 seconds.

---

## Warning System

`~warn <member> [reason]` issues a warning with a unique hex ID, DMs the member, and optionally triggers auto-threshold actions. Thresholds are configurable per server via `/warnthresholds` and support `timeout`, `kick`, and `ban` actions at specified warn counts. Warning history is stored in `warnings.db` per guild.

---

## Math

`~math <equation>` queries Wolfram|Alpha — Short Answer API first, LLM API as fallback. Results are formatted with bolded headers and a LaTeX-rendered image where applicable.

---

## Injection Detection

Prompt injection attempts (`"ignore previous instructions"`, `"jailbreak"`, `"developer mode"`, etc.) are caught by `utils/security.py` before reaching the model. The prompt is neutralized rather than silently dropped, and the output is also checked for injection artifacts in model responses.

---

## Hybrid Commands

Every command works as both a prefix command (`~write`) and a slash command (`/write`). The prefix is configurable per server and persists across restarts via `config.json`.

---

## Runtime Configuration

Most hardcoded timing and behavior constants have been moved into `config.json` and can be changed at runtime using `/config` commands (Bot Owner only). Changes persist across restarts and take effect immediately without a bot restart.

### Configurable Values



| Key                                      | Type   | Default      | Description                                           |
|:-----------------------------------------|:-------|:-------------|:------------------------------------------------------|
| `mvsep_poll_interval`                    | int    | 5            | Seconds between MVSEP API polling checks              |
| `mvsep_poll_timeout`                     | int    | 300          | Max seconds to wait for MVSEP task completion         |
| `ytdlp_subprocess_timeout`               | int    | 300          | Max seconds for yt-dlp subprocess to complete         |
| `ytdlp_compress_target_mb`               | float  | 9.5          | Target size in MB for video compression               |
| `generation_split_min_length`            | int    | 1900         | Minimum message length before splitting into segments |
| `generation_split_delay_base`            | float  | 0.5          | Base delay in seconds between message segments        |
| `generation_split_delay_per_char`        | float  | 0.001        | Additional delay per character in segment             |
| `generation_split_delay_max`             | float  | 3.0          | Maximum delay between segments in seconds             |
| `generation_rate_limit`                  | float  | 1.0          | Minimum seconds between AI generation calls           |
| `conversation_max_messages`              | int    | 20           | Max messages per conversation scope                   |
| `conversation_token_budget`              | int    | 4000         | Approximate token budget for conversation context     |
| `conversation_ttl_seconds`               | int    | 3600         | Time-to-live for conversations (seconds)              |
| `conversation_summary_threshold`         | int    | 15           | Message count before summarization                    |
| `character_memory_max_memories`          | int    | 50           | Max memories per (guild, user, persona) scope         |
| `character_memory_min_importance`        | float  | 0.3          | Minimum importance score for memory retention         |
| `character_memory_extraction_interval`   | int    | 300          | Seconds between extraction runs                       |
| `character_memory_extraction_batch_size` | int    | 10           | Conversations to process per extraction run           |
| `canon_version`                          | string | "1.0.0"      | Current canon version                                 |
| `canon_file_path`                        | string | "./canon.db" | Path to canon database                                |



### Commands



| Command                     | Action                                            | Permissions |
|:----------------------------|:--------------------------------------------------|:------------|
| `/config show [key]`        | Show all runtime config values, or a specific key | Bot Owner   |
| `/config list`              | List all configurable keys with descriptions      | Bot Owner   |
| `/config set <key> <value>` | Set a config value (auto type-converted)          | Bot Owner   |
| `/config reset <key>`       | Reset a config key to its default value           | Bot Owner   |



### Example Usage

```sc
/config show mvsep_poll_interval
/config set mvsep_poll_interval 10
/config set ytdlp_compress_target_mb 8.0
/config reset generation_rate_limit
```

Values are validated and type-converted based on their default types (int, float, bool, or string). Invalid values are rejected with an error message.
