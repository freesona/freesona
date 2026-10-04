# `utils/`

This document follows ASD-STE100 Simplified Technical English.

The `utils/` directory contains shared Freesona logic. Cogs import modules
from this directory. Cogs do not import other cogs directly.

| Module                        | Responsibility                                                                                                                    |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `anniversaries_db.py`         | Stores anniversary events and provides scheduling helpers.                                                                        |
| `canon.py`                    | Canon Framework — modular immutable identity components (identity, beliefs, motivations, rules, world assumptions, explanations). |
| `character_memory.py`         | Character Memory — persistent shared history (promises, jokes, experiences) per guild/user/persona.                               |
| `chroma.py`                   | ChromaDB integration for knowledge base ingestion and retrieval.                                                                  |
| `config.py`                   | Reads and writes `config.json`. Provides `embed_footer` and provider/model name accessors.                                        |
| `config_schema.py`            | Config key categories and descriptions for `/config list` and interactive panels.                                                 |
| `conversation.py`             | ConversationManager — provider-agnostic short-term memory with budgets, TTL, and cleanup.                                         |
| `generation.py`               | Generates responses, handles attachments, and injects prompts without provider-specific behavior.                                 |
| `guild_world.py`              | Guild World Context — environmental grounding (server name, channel, topic) as request-scoped context.                            |
| `ingest_pdf.py`               | PDF text extraction for knowledge base ingestion.                                                                                 |
| `intent.py`                   | Scores autonomy signals, maps scores to thresholds, and defines `IntentResult`.                                                   |
| `knowledge_base.py`           | KnowledgeBaseService — SQLite persistence and ChromaDB indexing for knowledge base entries.                                       |
| `logging_utils.py`            | Structured logging setup with section-based filtering and Discord channel output.                                                 |
| `message_claims.py`           | Message classification — identifies message types (user, bot, webhook) for conversation handling.                                  |
| `memory.py`                   | Stores long-term user facts in SQLite, keyed by `guild_id + user_id`.                                                             |
| `modules.py`                  | Defines the cog registry and manages optional modules.                                                                            |
| `persona.py`                  | Manages persona data, structured fields, the `/setpersona` panel, and saved profiles.                                             |
| `prompt_builder.py`           | PromptBuilder — assembles system prompts from ordered ContextProvider components.                                                 |
| `prompt_builder_providers.py` | ContextProvider implementations for persona, canon, conversation, memory, and retrieval.                                          |
| `providers.py`                | Shared provider abstraction — routes generation calls to Gemini, OpenAI, Ollama, NIM, Azure, Groq, or OpenRouter.                 |
| `roles.py`                    | Resolves a message author as a user, bot, or webhook.                                                                             |
| `rss.py`                      | Parses RSS and Atom XML, manages feeds, and tracks seen links.                                                                    |
| `search.py`                   | Searches the web with Gemini grounding. It can use Google Custom Search as a legacy fallback.                                     |
| `security.py`                 | Checks URLs for SSRF, detects and redacts prompt injection, checks output safety, and validates math ASTs.                        |

See [the architecture guide](../docs/architecture.md) for the system design.
