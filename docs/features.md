# Features

## Persona System

Freesona's persona is split into five structured fields edited through a button-based `/setpersona` panel — no restart required.

| Field | Edited via |
| :--- | :--- |
| Core Personality & Traits | `/setpersona` |
| Background & History | `/setpersona` |
| Beliefs, Likes & Dislikes | `/setpersona` |
| Language & Communication Style | `/setpersona` |
| System Instructions | `/setpersona` |

Changes take effect immediately. The assembled persona is injected as the system instruction on every generation call, assembled in XML-tagged blocks for clarity.

**Persona profiles** — save, load, list, and delete named presets with `/personasave`, `/personaload`, `/personalist`, `/personadelete`. Useful for switching between characters or server contexts.

**Persona lock** — `/personalock` prevents accidental overwrites. `/personaunlock` to re-enable editing.

**Legacy support** — if a `persona.txt` file exists and no `persona.json` is found, the bot falls back to it automatically. Existing installs don't break on upgrade.

**Debug** — `/debugpersona` shows the fully assembled persona, last prompt sent to the model, active provider and model, lock state, and autonomy status.

---

## Memory

### Short-term (provider continuity, optional)

Gemini conversation continuity is handled server-side via the Interactions API `previous_interaction_id`. The bot keeps the last continuity ID per `(guild_id, channel_id, user_id)` scope, so one user's Gemini thread does not bleed into another user's reply in the same channel. Other providers remain stateless by design and rely on prompt memory injection.

### Long-term (per user, per guild, persisted)

After each user message, the bot runs a background fact extraction pass — asking the active model whether the message reveals anything worth remembering (name, job, location, interests, projects, relationships). Facts are scored by importance (0.0–1.0), deduplicated by message ID, and capped at 20 per user. Facts below 0.3 importance are dropped. The top facts are injected into the system prompt for future conversations with that user.

Stored in `memory.db`, keyed by `guild_id + user_id`. Survives restarts and is provider-neutral.

### User distinction

Every message payload is tied to a stable Discord `user_id` before reaching the model. The bot uses that identity key to keep memory isolated per user, even in busy multi-user channels.

---

## Multiple AI Providers

Freesona routes generation through a provider abstraction so the same commands can target different backends without changing command code. Supported providers:

| Provider | Key env var |
| :--- | :--- |
| Gemini (default) | `GOOGLE_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Ollama | `OLLAMA_BASE_URL` |
| NVIDIA NIM | `NVIDIA_API_KEY` |
| Azure AI Foundry | `AZURE_AI_KEY`, `AZURE_AI_BASE_URL` |
| Groq | `GROQ_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |

Set `AI_PROVIDER` and `AI_PROVIDER_MODEL` in `.env`, then add the matching credentials. `/model set` and `/model reset` change the active model at runtime without a restart. The provider abstraction is shared across Gemini, OpenAI, Ollama, NVIDIA NIM, Azure AI Foundry, Groq, and OpenRouter; Gemini-only continuity is optional and should not be assumed for provider-neutral memory behavior.

---

## ChromaDB Knowledge Base

An optional ChromaDB-backed retrieval layer is available for semantic lookups during generation. When enabled, relevant documents from the local vector store are injected into the system prompt context alongside user facts and the active persona.

Configure with `CHROMA_COLLECTION` and `CHROMA_PERSIST_DIRECTORY` in `.env`. The retrieval path is fully optional — if ChromaDB is not installed or the collection is empty, generation continues normally.

The local KB now exposes `/kbsearch`, `/kbadd`, `/kblist`, and `/kbdelete` on top of that retrieval foundation for simple management from Discord.

---

## Anniversary Tracking

`utils/anniversaries_db.py` provides a generic SQLite-backed anniversary entry system. Each entry stores a title, subtitle, anniversary date, optional thumbnail and reference URL, and an optional calendar event ID for external calendar sync.

The database supports per-guild user entries, duplicate detection, date-based lookups, and queries for entries missing calendar sync or thumbnails. The full user-facing cog that drives claiming and announcements is a separate private implementation built on top of this shared layer.

---

## Autonomous Mode

When enabled, the bot can join an active conversation unprompted. It uses a confidence-scored intent evaluator (`utils/intent.py`) rather than a random dice roll:

| Signal | Score |
| :--- | :--- |
| Direct mention or reply to bot | +0.90 |
| Attachment present | +0.50 |
| Code block present | +0.40 |
| Semantic trigger word (what, how, explain, fix…) | +0.40 |
| Ends with question mark | +0.20 |
| Channel has existing conversation memory | +0.10 |
| Short filler message (lol, ok, emoji-only) | −0.30 |
| Long monologue with no question and no mention | −0.20 |

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

`~math <equation>` queries Wolfram\|Alpha — Short Answer API first, LLM API as fallback. Results are formatted with bolded headers and a LaTeX-rendered image where applicable.

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

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `mvsep_poll_interval` | int | 5 | Seconds between MVSEP API polling checks |
| `mvsep_poll_timeout` | int | 300 | Max seconds to wait for MVSEP task completion |
| `ytdlp_subprocess_timeout` | int | 300 | Max seconds for yt-dlp subprocess to complete |
| `ytdlp_compress_target_mb` | float | 9.5 | Target size in MB for video compression |
| `generation_split_min_length` | int | 1900 | Minimum message length before splitting into segments |
| `generation_split_delay_base` | float | 0.5 | Base delay in seconds between message segments |
| `generation_split_delay_per_char` | float | 0.001 | Additional delay per character in segment |
| `generation_split_delay_max` | float | 3.0 | Maximum delay between segments in seconds |
| `generation_rate_limit` | float | 1.0 | Minimum seconds between AI generation calls |

### Commands

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/config show [key]` | Show all runtime config values, or a specific key | Bot Owner |
| `/config list` | List all configurable keys with descriptions | Bot Owner |
| `/config set <key> <value>` | Set a config value (auto type-converted) | Bot Owner |
| `/config reset <key>` | Reset a config key to its default value | Bot Owner |

### Example Usage

```
/config show mvsep_poll_interval
/config set mvsep_poll_interval 10
/config set ytdlp_compress_target_mb 8.0
/config reset generation_rate_limit
```

Values are validated and type-converted based on their default types (int, float, bool, or string). Invalid values are rejected with an error message.
