# Architecture

This document explains how Freesona is structured internally. It is intended for developers who want to understand the codebase, extend it, or debug it.

---

## Component Layout

```text
Freesona/
├── main.py                   # Bot startup, intents, prefix, on_ready, HTTP server (port via HTTP_PORT env var, default 10000)
├── fastapi_server.py         # FastAPI health + MVSEP webhook receiver
├── cogs/
│   ├── ai/
│   │   └── genai.py          # AI commands (ask, write, search), autonomy, persona/memory management
│   ├── media/
│   │   ├── mvsep.py          # Audio stem separation via MVSEP API
│   │   └── ytdlp.py          # Video/audio downloader via yt-dlp + ffmpeg
│   ├── moderation/
│   │   ├── core.py           # Kick, ban, timeout, purge
│   │   └── warns.py          # Warn, delwarn, warnthresholds
│   ├── system/
│   │   ├── admin.py          # Module, model, provider, sync, timezone, dumpconfig
│   │   ├── help.py           # Custom help panel
│   │   ├── news.py           # RSS/Atom feed fetching and auto-posting
│   │   └── status.py         # /ping
│   ├── tools/
│   │   ├── math.py           # Local SymPy solver + Wolfram Alpha fallback + plot
│   │   └── ping.py           # Latency probe
│   └── fun/
│       ├── hello.py          # ~hello
│       └── random.py         # coinflip, roll, pick, randommember
└── utils/
    ├── config.py             # Config I/O (config.json), embed_footer
    ├── generation.py         # Gemini API calls, ConversationResponse, send_response
    ├── intent.py             # Confidence-scored intent evaluator for autonomy
    ├── memory.py             # SQLite long-term facts + per-channel interaction ID store
    ├── modules.py            # Cog registry (OPTIONAL_MODULES, CORE_EXTENSIONS)
    ├── persona.py            # Persona data layer, /setpersona panel modals
    ├── roles.py              # Role resolution for message author tagging
    ├── rss.py                # RSS/Atom XML parser, feed CRUD, seen-link deduplication
    ├── search.py             # Gemini grounding + Google Custom Search fallback
    └── security.py           # URL guard, injection detection, output sanitization
```

All cogs depend on `utils/`. Cogs do not import from each other, except that `mvsep.py` calls `ytdlp.py` via `bot.get_cog("YtDlp")` (not a direct import) to download platform audio before submitting to MVSEP.

---

## Message Lifecycle

Every incoming Discord message that the bot sees passes through a linear pipeline inside `GenAICog.on_message`:

```text
Discord Message
      │
      ▼
[1. Hard filters]
  - Message is from a guild (not DM)?
  - Message type is default or reply?
  - Not a slash command interaction?
  - Not a prefix command (ctx.valid)?
  - Not the bot itself?
  - Not a non-whitelisted bot?
      │
      ▼
[2. Route: Conversation Channel?]
  config["chat_channel_id"] == message.channel.id
      │                │
     Yes              No ──────────────────────────────────────┐
      │                                                        │
      ▼                                                        ▼
[3a. Conversation channel path]                 [3b. Autonomy path]
  Check conversation_response_mode               autonomy_on and role == "user"?
  ("all" / "mentions" / "smart")                Check per-channel + per-user cooldowns
      │                                          Evaluate intent (evaluate_intent)
      ▼                                          confidence >= frequency_threshold?
  Debounce (1.2s per user)                              │
  Collapse rapid messages                              Yes
      │                                                │
      ▼                                                ▼
[4. Generate]  ◄─────────────────────────────────[Generate]
  safe_generate(payload, persona, channel_id, guild_id, user_id, ...)
      │
      ▼
[5. send_response → split long text into chunks → send embeds/files]
```

### Debounce

Messages in the conversation channel are held for 1.2 seconds before generating a response. If the same user sends another message within that window, the first task is cancelled and the timer resets. This prevents the bot from responding to mid-thought partial messages.

---

## Generation Pipeline (`utils/generation.py`)

`safe_generate` wraps the active provider call with:

1. **Security pre-check** — `detect_injection(prompt)`: if the prompt contains a known injection attempt, `sanitize_prompt` redacts the matched phrase(s) before sending.
2. **Persona injection** — `assemble_persona(PERSONA_DATA)` builds the system instruction from five structured fields.
3. **Memory injection** — `get_user_facts_prompt(guild_id, user_id)` prepends known long-term facts to the system prompt.
4. **Conversation continuity** — `get_interaction_id(guild_id, channel_id, user_id)` retrieves the most recent provider-specific continuity token for that user-only scope when available; Gemini uses `previous_interaction_id` for server-side conversation continuity, while other providers remain stateless.
5. **Attachment multimodal processing** — `extract_attachments(message)` downloads and encodes images/PDFs/audio/video for the active provider's multimodal input pipeline when supported.
6. **Response storage** — the returned Gemini `interaction_id` is saved via `set_interaction_id(guild_id, channel_id, user_id, ...)` so a single user’s continuity chain stays isolated.
7. **Output safety** — `unsafe_output(text)` checks the model's response for injection artifacts before sending.

---

## Memory System (`utils/memory.py`)

### Short-term (provider continuity, in-session)

Conversation history is managed **server-side** by Gemini's Interactions API via `previous_interaction_id` when the active provider supports it. The bot stores continuity per `(guild_id, channel_id, user_id)` rather than one global ID per channel, which keeps user-specific threads isolated. Non-Gemini providers do not assume this continuity path. Cleared via `/clearmemory` or on restart.

### Long-term (per-user, SQLite)

After each user message, a background task runs `extract_and_store_fact`. This makes a stateless Gemini call asking:

> *"Does this message reveal any fact worth remembering? Respond with `{content, importance}` or `null`."*

Facts with `importance >= 0.3` are stored in `memory.db`, keyed by `(guild_id, user_id)`. The top 20 facts per user (by importance) are kept. Facts are injected into the system prompt as a `[Known facts about {display_name}]` block.

**DB schema:**

```sql
user_facts (
    guild_id   TEXT,
    user_id    TEXT,
    content    TEXT,
    importance REAL,   -- 0.0–1.0
    timestamp  TEXT,
    message_id TEXT PRIMARY KEY,
    channel_id TEXT
)
```

---

## Autonomy Flow (`utils/intent.py`)

When autonomy mode is enabled, the bot evaluates every message in non-conversation channels using a confidence-scored heuristic:

| Signal | Score |
| :--- | :--- |
| Direct mention or reply to bot | +0.90 |
| Attachment present | +0.50 |
| Code block present | +0.40 |
| Semantic trigger word (what, how, fix, explain…) | +0.40 |
| Ends with question mark | +0.20 |
| Channel has existing interaction memory | +0.10 |
| Short filler message (lol, ok, emoji-only) | −0.30 |
| Long monologue, no question and no mention | −0.20 |

Confidence is clamped to `[0.0, 1.0]`. The bot fires only if:

- `confidence >= frequency_threshold` (low = 0.70, default = 0.50, high = 0.35)
- Per-channel cooldown (120s) has elapsed
- Per-user cooldown (60s) has elapsed

---

## Persona System (`utils/persona.py`)

The persona is stored as a structured JSON object with five fields:

| Field | Key |
| :--- | :--- |
| Core Personality & Traits | `core` |
| Background & History | `background` |
| Beliefs, Likes & Dislikes | `beliefs` |
| Language & Communication Style | `style` |
| System Instructions | `instructions` |

`assemble_persona(data)` combines these into a single system instruction string injected on every generation call. Edits via `/setpersona` (a Discord modal UI) take effect immediately without restarting.

**Profiles** (`personas.json`) let you save and restore complete persona snapshots by name.

---

## Persona Knowledge Base (RAG) (`utils/chroma.py`, `utils/generation.py`)

### Definition

**Persona Knowledge Base (PKB)** is the retrieval subsystem responsible for supplying canonical persona knowledge to the generation pipeline. It stores structured knowledge about a persona and provides relevant context during generation. It does not manage conversation state, user memory, or prompt construction.

### Purpose

The knowledge base stores **canonical, factual information** about a persona — dialogue, narration, events, relationships, and descriptions — sourced from original material (anime, novels, manga, games, etc.). It supplies canonical knowledge about a persona as one input to the generation pipeline and does not independently determine model behavior. It is **not** responsible for:
- Conversation history (handled by provider continuity)
- User long-term memory (handled by `utils/memory.py`)
- Persona definition/prompt engineering (handled by `utils/persona.py`)
- Safety instructions or model reasoning

### Architecture

```
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

```
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

| Field | Description |
|-------|-------------|
| `schema_version` | Schema version of the entry (default: `1`) |
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
| Field | Description |
|-------|-------------|
| `persona` | Persona identifier (e.g., `chisato_nishikigi`) |
| `source` | Original source reference (e.g., `Episode 06`, `Chapter 12`) |
| `source_type` | Media type: `anime`, `novel`, `manga`, `game`, `guidebook`, `interview`, `website`, `other` |
| `entry_type` | Content type: `dialogue`, `narration`, `event`, `relationship`, `description` |
| `topics` | Semantic topics for retrieval (non-empty list) |

#### Optional Metadata Fields
| Field | Description |
|-------|-------------|
| `episode` | Episode number |
| `chapter` | Chapter number |
| `scene` | Scene description |
| `speaker` | Speaking character (for dialogue) |
| `timestamp` | Source timestamp (e.g., `2023-01-15`, `S01E06 12:34`) |
| `canon_level` | Canon priority: `canon`, `semi-canon`, `non-canon`, `headcanon`, `alternate` |
| `tags` | Additional indexing tags (comma-separated) |

### Ingestion Pipeline

The ingestion pipeline (`utils/chroma.py`) provides utilities for deterministic, reproducible ingestion:

1. **`clean_source_text(text)`** — Normalizes line endings, removes excessive blank lines
2. **`identify_speakers(text, patterns?)`** — Extracts speaker-attributed dialogue lines
3. **`chunk_semantic_units(text, max_size, min_size, speaker_data?)`** — Splits text into atomic semantic chunks (one exchange, one event, one monologue)
4. **`assign_metadata(chunks, base_metadata)`** — Applies base metadata + chunk-specific fields (speaker → `entry_type: dialogue`)
5. **`ingest_source(raw_text, base_metadata, ...)`** — Full pipeline: clean → identify → chunk → assign metadata

Each stage is deterministic and can be tested independently.

### Retrieval & Context Construction

The retrieval function `retrieve_knowledge_context(query, persona, top_k)` in `utils/generation.py`:

1. Embeds the user's message
2. Queries ChromaDB with **metadata filtering (by `persona`) occurring before or alongside vector search** to reduce the candidate set
3. Returns the **most relevant k entries** (where `k` is configurable via `kb_top_k`, default 5)
4. An optional re-ranking stage can be added later without changing the overall architecture
5. Assembles context in the **Relevant Canonical Context** format:

```
Relevant Canonical Context
1. Document text...
   (Source: Episode 06, Type: dialogue, Scene: Aquarium, Speaker: Chisato, Chapter: , Timestamp: S01E06 12:34, Canon: canon)
2. Document text...
   (Source: Chapter 12, Type: narration, Scene: , Speaker: , Chapter: Chapter 12, Timestamp: , Canon: canon)
```

This context is appended to the persona prompt **after** long-term memory, following the priority order:
```
System Prompt
Persona Definition
Conversation Memory
Long-Term Memory (User Facts)
Persona Knowledge Base (RAG)
Generation
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
- `kb_top_k` — Number of entries to retrieve (default: `5`)
- `kb_collection` — Override collection name
- `kb_persist_directory` — Override storage path

---

## Module System (`utils/modules.py`)

Cogs are split into **core** (always loaded) and **optional** (can be toggled at runtime without restart):

```python
CORE_EXTENSIONS = [help, ping, status, admin]
OPTIONAL_MODULES = {genai, math, news, ytdlp, mvsep, moderation, warns, hello, random}
```

Enabled/disabled state persists in `config.json` under `"enabled_modules"`. The `/module enable`, `/module disable`, and `/module reload` commands call `bot.load_extension` / `unload_extension` / `reload_extension` at runtime and re-sync slash commands automatically.

**Dependency guard:** `mvsep` requires `ytdlp` — the admin cog enforces this at enable/disable time.

> [!NOTE]
> `/provider set` now routes through the shared provider abstraction in `utils/providers.py`. Gemini uses server-side continuity when available; all other providers remain stateless and rely on the prompt plus the current user memory snapshot for context.

---

## Media Integrations

### yt-dlp (cogs/media/ytdlp.py)

Downloads video or audio via yt-dlp + ffmpeg into a temp directory. Resolution ladder: 1080p → 720p → 480p → FFmpeg compressed. Audio extraction produces MP3. Platform-specific cookies can be supplied via `COOKIES_<PLATFORM>` env vars.

### MVSEP (cogs/media/mvsep.py)

Submits audio to the MVSEP BS Roformer model for vocal/instrumental separation:

1. **Input resolution** — attachment > direct audio URL > yt-dlp download
2. **Job submission** — POST to `mvsep.com/api/separation/create`
3. **Result waiting** — Webhook (`MVSEP_WEBHOOK_URL`) if configured, otherwise polling every 10s (timeout: 10 min)
4. **Output** — Embed with labeled download links (Vocals / Instrumental)

`fastapi_server.py` receives MVSEP webhooks at `/webhooks/mvsep` and resolves the corresponding `asyncio.Future` registered by `mvsep.py`.

### Wolfram Alpha (cogs/tools/math.py)

Math query routing:

1. Local SymPy evaluation — if the expression is safe and simplifiable
2. Wolfram Short Answer API (`/v1/result`)
3. Wolfram LLM API (`/api/v1/llm-api`) as final fallback

Expressions are validated by an AST-level safety checker (`is_safe_expression`) before passing to SymPy, blocking any attempt to execute system calls or import modules.

---

## Security (`utils/security.py`)

| Layer | What it guards |
| :--- | :--- |
| `is_public_http_url(url)` | Blocks SSRF — rejects private/loopback IPs, obfuscated forms (hex, octal, decimal int), non-HTTP schemes, localhost, and cloud metadata endpoint (169.254.169.254) |
| `detect_injection(prompt)` | Pattern matches against known prompt injection phrases ("ignore previous instructions", "jailbreak", etc.) |
| `sanitize_prompt(prompt)` | Redacts matched injection phrases before forwarding to the model (does not just flag; actively removes) |
| `unsafe_output(text)` | Checks model output for injection echo artifacts |
| `is_safe_expression(expr)` | AST-level allowlist for SymPy expressions — blocks `eval`, `exec`, `import`, `__dunder__` access, and any call not in `SAFE_FUNCTIONS` |

---

## FastAPI Server (`fastapi_server.py`)

The FastAPI server runs in a background async task (via `asyncio.gather`) alongside the Discord bot.

Current endpoints:

| Endpoint | Purpose |
| :--- | :--- |
| `GET /` | Heartbeat — returns `{"status": "ok"}` |
| `GET /health` | Health check for uptime monitors |
| `POST /webhooks/mvsep` | MVSEP separation result callback |

Future endpoints (planned in roadmap):

- `/instance/status` — multi-instance presence
- `/message/claim` + `/message/release` — ownership coordination
- Web dashboard for config management

---

## Config (`config.json`)

All runtime-mutable settings are stored in `config.json`. Loaded fresh on every command via `load_config()` to avoid stale state across module reloads.

| Key | Type | Description |
| :--- | :--- | :--- |
| `prefix` | str | Command prefix (default: `~`) |
| `chat_channel_id` | int | Conversation channel ID |
| `conversation_response_mode` | str | `all` / `mentions` / `smart` |
| `autonomy` | bool | Autonomy mode enabled |
| `autonomy_frequency` | str | `low` / `default` / `high` |
| `model_name` | str | Active Gemini model |
| `provider` | str | Active AI provider |
| `timezone` | str | IANA timezone string |
| `enabled_modules` | dict | Per-module enabled state |
| `whitelist_bot_ids` | list[int] | Bot IDs allowed through on_message filter |
| `rss_feeds` | dict | Custom feed name → URL |
| `rss_disabled` | list[str] | Disabled built-in feed keys |
| `rss_seen` | list[str] | Seen article links (dedup, capped at 500) |

---

## Environment Variables

See `.env.sample` for a full reference. Key variables:

| Variable | Required | Description |
| :--- | :--- | :--- |
| `BOT_TOKEN` | ✅ | Discord bot token |
| `CHANNEL_ID` | ✅ | Startup message channel |
| `GOOGLE_API_KEY` | ✅ | Gemini API key |
| `MODEL_NAME` | ✅ | Default Gemini model |
| `CONFIG_FILE_PATH` | ✅ | Path to `config.json` |
| `MEMORY_FILE_PATH` | ✅ | Path to `memory.db` |
| `BOT_NAME` | — | Display name for startup messages |
| `WOLFRAM_APPID_SHORT` | — | Wolfram Short Answer API key |
| `WOLFRAM_APPID_LLM` | — | Wolfram LLM API key |
| `MVSEP_API_KEY` | — | MVSEP separation API key |
| `MVSEP_WEBHOOK_URL` | — | Public URL for MVSEP callbacks |
| `COOKIES_<PLATFORM>` | — | Netscape cookies file for yt-dlp auth |
| `GOOGLE_SEARCH_API_KEY` | — | Legacy Google Custom Search fallback |
| `SEARCH_ENGINE_ID` | — | Legacy Google Custom Search engine ID |

---

## Pre-push Checks

Run before pushing to verify syntax, config round-trip, URL guards, and all unit tests:

```bash
# Linux/macOS
./scripts/check.sh

# Windows PowerShell (auto-detects .venv)
.\scripts\check.ps1

# Directly
python scripts/check_project.py
```

To enable automatic checks on `git push`:

```bash
git config core.hooksPath .githooks
```

---

## Adding a New Cog

1. Create `cogs/<category>/<name>.py` with a `setup(bot)` coroutine.
2. Add a `"<name>": "cogs.<category>.<name>"` entry to `OPTIONAL_MODULES` in `utils/modules.py`.
3. It will appear in `/module list` and can be enabled/disabled at runtime.
4. Add it to `docs/commands.md` and `docs/features.md` if it adds user-facing commands.
