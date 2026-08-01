<!-- markdownlint-disable MD033 -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/bd_freesona.png">
  <img src="assets/bl_freesona.png" alt="Freesona Banner">
</picture>
<!-- markdownlint-enable MD033 -->

# Freesona

All repository documentation must adhere to ASD-STE100 Simplified Technical
English.

Freesona is an open-source, self-hosted Discord AI bot. It keeps persona,
conversation, long-term memory, knowledge, and environment as separate systems.

Provide an API key, select an AI provider, and run the bot on your own
infrastructure. Use Freesona to build a character, server companion, or utility
bot with a defined persona.

Freesona uses the **BYOK** (Bring Your Own Key) model. The selected provider
and your infrastructure set the available capacity and cost.

→ [Features](docs/features.md) · [Commands](docs/commands.md) · [Discord](https://discord.gg/vXPRs2cHSE)

---

## Main features

- User Memory stores user facts in SQLite. The `guild_id + user_id` key keeps
  facts separate between Discord servers.
- Character Memory stores shared experiences for a guild, user, and persona.
  It works across channels in the same server.
- ChromaDB can get relevant knowledge and add it to a generation request.
- `ConversationManager` owns conversation history. AI providers remain
  stateless and receive the same context through the system prompt.
- A per-user, per-channel debounce combines rapid messages into one response.
- Autonomous mode evaluates message intent and applies a per-channel cooldown.
- The bot can process images, PDFs, audio, video, and code files.
- The shared provider interface supports Gemini, OpenAI, Ollama, NVIDIA NIM,
  Azure AI Foundry, Groq, and OpenRouter.
- The optional knowledge base provides `/kbsearch`, `/kbadd`, `/kblist`, and
  `/kbdelete` commands.
- Shared logic is in `utils/`. See [the utilities guide](utils/README.md).

---

## Getting Started

1. Clone the repository and create a virtual environment.

```bash
git clone https://github.com/soquincy/Freesona.git
cd Freesona
python3 -m venv .venv
```

1. Activate the environment and install the dependencies.

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

For Windows PowerShell, run:

```powershell
.\.venv\Scripts\activate.ps1
pip install -r requirements.txt
```

```cmd
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

On some Windows installations, Python `zoneinfo` does not include IANA time
zone data. Install `tzdata` so `/settimezone` and other `ZoneInfo` calls work.

```powershell
pip install tzdata
```

`requirements.txt` includes `tzdata`. The dependency-installation command adds
it to a new environment.

Before pushing changes, run the local checks:

```bash
python scripts/check_project.py
```

On Windows PowerShell, you can also run:

```powershell
.\scripts\check.ps1
```

To make Git run the checks before pushes to `dev`, enable the included hook once:

```bash
git config core.hooksPath .githooks
```

For a local desktop/self-hosted setup, use the included runner helpers instead of Docker or Railway-specific workflows:

- `bash scripts/setup_local.sh`
- `scripts\setup_local.cmd`

These scripts create `.env` from `.env.sample` on first run, validate the required Discord IDs and selected provider keys, install local dependencies into `.venv`, run the project checks, and then launch the bot.

> These helpers are for local/manual hosting only. They are not intended for Docker, Railway, Render, or any other automated deployment environment where the platform should own the bootstrap process.

Create a `.env` file:

```dotenv
# HTTP Server
HTTP_PORT=10000

# Discord
BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
CHANNEL_ID=YOUR_LOG_CHANNEL_ID
BOT_NAME=Freesona

# AI Provider
AI_PROVIDER=          # gemini | openai | ollama | nim | azure | groq | openrouter
AI_PROVIDER_MODEL=          # override the default model for the chosen provider
MODEL_NAME=gemini-flash-lite-latest
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY

# Provider API keys (set the one matching your AI_PROVIDER)
# OPENAI_API_KEY=
# OPENAI_BASE_URL=https://api.openai.com/v1/chat/completions
# OLLAMA_BASE_URL=http://localhost:11434/api/chat
# NVIDIA_API_KEY=
# NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1/chat/completions
# AZURE_AI_KEY=
# AZURE_AI_BASE_URL=        # your Azure AI Foundry endpoint
# GROQ_API_KEY=
# OPENROUTER_API_KEY=
# OPENROUTER_SITE_URL=
# OPENROUTER_SITE_NAME=Freesona

# ChromaDB (optional — required for knowledge base retrieval)
CHROMA_COLLECTION=freesona
CHROMA_PERSIST_DIRECTORY=./.chroma

# Complimentary tokens
MVSEP_API_KEY=YOUR_MVSEP_API_KEY
MVSEP_WEBHOOK_URL=https://your-public-host.example.com/webhooks/mvsep
MVSEP_WEBHOOK_SEND_MAIL_ON_ERROR=false
WOLFRAM_APPID_SHORT=YOUR_WOLFRAM_APPID_SHORT
WOLFRAM_APPID_LLM=YOUR_WOLFRAM_APPID_LLM

# File paths (local)
AI_PERSONA_FILE=persona.txt
AI_PERSONA_JSON_FILE=persona.json
AI_PERSONAS_FILE=personas.json
AI_PERSONA=You are a helpful assistant.
CONFIG_FILE_PATH=config.json
MEMORY_FILE_PATH=memory.db
WARNINGS_FILE_PATH=warnings.db
ANNIVERSARIES_FILE_PATH=anniversaries.db

# File paths (cloud — Railway/Render, requires /data volume mount)
# AI_PERSONA_FILE=/data/persona.txt
# AI_PERSONA_JSON_FILE=/data/persona.json
# AI_PERSONAS_FILE=/data/personas.json
# CONFIG_FILE_PATH=/data/config.json
# MEMORY_FILE_PATH=/data/memory.db
# WARNINGS_FILE_PATH=/data/warnings.db
# ANNIVERSARIES_FILE_PATH=/data/anniversaries.db
```

| Environment | Path prefix | Notes                                     |
|:------------|:------------|:------------------------------------------|
| **Local**   | `./`        | Files saved in project folder             |
| **Railway** | `/data/`    | Requires volume mounted to `/data`        |
| **Render**  | `/data/`    | Create files manually in environment page |

Without a persistent volume on cloud hosts, file changes won't survive a redeployment.

---

## Persistence & Storage

| File                  | What it stores                                                                                                                   |
|:----------------------|:---------------------------------------------------------------------------------------------------------------------------------|
| `config.json`         | Prefix, conversation channel, autonomy settings, module states                                                                   |
| `persona.json`        | Active persona fields                                                                                                            |
| `personas.json`       | Saved persona presets                                                                                                            |
| `memory.db`           | Long-term user facts, keyed by `guild_id + user_id` for provider-neutral memory injection                                        |
| `character_memory.db` | Character Memory — shared experiences, promises, recurring jokes, relationship progression (per guild/user/persona)              |
| `canon.db`            | Canon Framework — modular immutable identity components (identity, beliefs, motivations, rules, world assumptions, explanations) |
| `warnings.db`         | Per-guild moderation warnings with hex IDs and timestamps                                                                        |
| `anniversaries.db`    | User-claimed anniversary entries with optional calendar sync metadata                                                            |
| `.chroma/`            | ChromaDB vector store for knowledge base retrieval (optional)                                                                    |

Conversation history is maintained by **ConversationManager** (provider-agnostic, in SQLite). Clear it per-channel with `/clearmemory`.

---

## Runtime Controls

Admins can control optional modules without editing `main.py`:

The `genai` module is an aggregate loader that registers AI commands by type-specific cogs (listener, generation, persona, memory, channel, autonomy).

```text
/module list
/module enable <name>
/module disable <name>
/module reload <name>
```

The bot owner can switch providers and models without restarting, sync global slash commands, and inspect the active config:

```text
/model show
/model set <model>
/model reset
/sync
/dumpconfig
```

Timezone and autonomy are also configurable at runtime:

```text
/settimezone <timezone>
/timezone
/autonomy on
/autonomy off
/autonomy frequency <low/default/high>
/chatmode all
/chatmode mentions
/chatmode smart
```

RSS/Atom feeds can be read and managed with:

```text
/rss list
/rss latest <feed>
/rss add <name> <url>
/rss remove <name>
/rss setchannel <#channel>
/rss clearchannel
```

---

## Acknowledgements

- [discord.py](https://discordpy.readthedocs.io/)
- [Google Gemini](https://ai.google.dev/)
- [OpenAI](https://platform.openai.com/)
- [Ollama](https://ollama.com/)
- [NVIDIA NIM](https://developer.nvidia.com/nim)
- [Azure AI Foundry](https://ai.azure.com/)
- [Groq](https://groq.com/)
- [OpenRouter](https://openrouter.ai/)
- [ChromaDB](https://www.trychroma.com/)
- [Wolfram\|Alpha](https://developer.wolframalpha.com/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [MVSEP](https://mvsep.com/)

---

## License

Licensed under the **MIT License**. See [LICENSE](LICENSE).

---

## Roadmap

### Completed

- [x] Provider abstraction — swap AI providers without changing command code (Gemini, OpenAI, Ollama, NVIDIA NIM, Azure AI Foundry, Groq, OpenRouter)
- [x] RSS monitors — post matching feed items into selected channels
- [x] Warning system — per-guild moderation warnings with hex IDs, auto-threshold actions, and DM notifications
- [x] Anniversary tracking — generic `anniversaries.db` backend for user-claimed date entries with optional calendar sync
- [x] Full knowledge base commands — `/kbadd`, `/kblist`, `/kbdelete` on top of the existing ChromaDB retrieval layer
- [x] **ConversationManager** — Provider-agnostic short-term memory with budgets, TTL, and prompt injection
- [x] **PromptBuilder** — Modular ContextProvider architecture with explicit ordering and inspection
- [x] **Canon Framework** — Modular immutable identity components (identity, beliefs, motivations, rules, world assumptions, explanations)
- [x] **Character Memory** — Shared experiences, promises, relationship progression (guild-scoped, cross-channel)
- [x] **Guild World Context** — Environmental grounding (server name, channel, topic) as request-scoped context
- [x] **Canonical Truth Invariant** — Architectural boundary: only Canon and PKB may define objective facts

### Short-term

- [x] Optional generation logging — local-only logs for abuse reporting and debugging; disabled by default, no data leaves the host; configurable Discord channel and 3-month rotating file output
- [x] Granular logging sections — per-section enable/disable (AI, Memory, Media, Moderation, Security, Webhook, General, Config) via `/logging` commands

### Medium-term

- [ ] Web dashboard via FastAPI — `fastapi_server.py` is already in the repo
- [ ] Message claiming system for multi-instance deployments

### Long-term

- [ ] Knowledge Base 2.0 — Structured entry types (Canon Scene, Character Profile, World Rule, etc.) with rich metadata
- [ ] Improved KB authoring tooling — deterministic ingestion, validation, and formatting guides

---

### AI-assisted development notice

- *This project is developed using AI coding assistants as part of the development workflow. AI is used to accelerate implementation, refactoring, testing, and documentation, while architectural decisions, project philosophy, and final code review remain under human control. Generated code is reviewed, tested, and may be modified before inclusion.*
