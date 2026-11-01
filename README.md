<!-- markdownlint-disable MD033 -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/bd_freesona.png">
  <img src="assets/bl_freesona.png" alt="Freesona Banner">
</picture>
<!-- markdownlint-enable MD033 -->

# Freesona

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.7.1-blue.svg)](https://discordpy.readthedocs.io/)
[![Discord](https://img.shields.io/badge/Discord-Join%20server-5865F2?logo=discord&logoColor=white)](https://discord.gg/KVFFDgxydW)

Freesona is an open-source, self-hosted Discord AI bot. It keeps persona,
conversation, long-term memory, knowledge, and environment as separate systems.

Provide an API key, select an AI provider, and run the bot on your own
infrastructure. Use Freesona to build a character, server companion, or utility
bot with a defined persona.

Freesona uses the **BYOK** (Bring Your Own Key) model. The selected provider
and your infrastructure set the available capacity and cost.

→ [Features](docs/features.md) · [Commands](docs/commands.md) · [Configuration](docs/configuration.md) · [Storage](docs/storage.md) · [Runtime Controls](docs/runtime.md) · [Architecture](docs/architecture.md) · [Discord](https://discord.gg/vXPRs2cHSE)

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
git clone https://github.com/freesona/freesona
cd freesona
python3 -m venv .venv
```

1. Activate the environment and install dependencies.

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

For Windows PowerShell:

```powershell
.\.venv\Scripts\activate.ps1
pip install -r requirements.txt
```

For Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

1. Copy `.env.sample` to `.env` and set your Discord bot token and AI provider
   API key.

2. Run the local checks before pushing changes:

```bash
python scripts/check_project.py
```

For a local desktop/self-hosted setup, use the included runner helpers:

- `bash scripts/setup_local.sh`
- `scripts\setup_local.cmd`

These scripts create `.env` from `.env.sample`, validate required IDs and keys,
install dependencies, run project checks, and launch the bot. They are for
local/manual hosting only, not for Docker, Railway, Render, or other automated
deployment environments.

To make Git run the checks before pushes to `dev`:

```bash
git config core.hooksPath .githooks
```

See [Configuration](docs/configuration.md) for the full environment variable
reference and [Storage](docs/storage.md) for file path details.

---

## Documentation

- [Features](docs/features.md) — Feature overview
- [Commands](docs/commands.md) — Command reference
- [Configuration](docs/configuration.md) — Environment variables
- [Storage](docs/storage.md) — Persistence and databases
- [Runtime Controls](docs/runtime.md) — Runtime commands
- [Architecture](docs/architecture.md) — Internal structure

---

## License

Licensed under the **MIT License**. See [LICENSE](LICENSE).

## Acknowledgements

Freesona integrates the [Delphitools CLI](https://github.com/1612elphi/delphitools-cli), licensed under the [0BSD License](https://opensource.org/licenses/0BSD), for image conversion, color simulation, and utility commands.

---

### AI-assisted development notice

This project is developed using AI coding assistants as part of the development
workflow. AI is used to accelerate implementation, refactoring, testing, and
documentation, while architectural decisions, project philosophy, and final code
review remain under human control. Generated code is reviewed, tested, and may
be modified before inclusion.
