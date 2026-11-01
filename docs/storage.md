# Persistence & Storage

This document follows ASD-STE100 Simplified Technical English.

This document describes the files and databases Freesona uses to persist data.

## File and database reference

| File | What it stores |
| :--- | :--- |
| `config.json` | Prefix, conversation channel, autonomy settings, module states |
| `persona.json` | Active persona fields |
| `personas.json` | Saved persona presets |
| `memory.db` | Long-term user facts, keyed by `guild_id + user_id` for provider-neutral memory injection |
| `knowledge.db` | Structured Knowledge Base records and Chroma index identifiers |
| `character_memory.db` | Character Memory — shared experiences, promises, recurring jokes, relationship progression (per guild/user/persona) |
| `canon.db` | Canon Framework — modular immutable identity components (identity, beliefs, motivations, rules, world assumptions, explanations) |
| `warnings.db` | Per-guild moderation warnings with hex IDs and timestamps |
| `anniversaries.db` | User-claimed anniversary entries with optional calendar sync metadata |
| `.chroma/` | ChromaDB vector store for knowledge base retrieval (optional) |

## Conversation history

Conversation history is maintained by **ConversationManager** (provider-agnostic, in SQLite). Clear it per-channel with `/clearmemory`.

## Multi-instance deployments

For multiple bot instances, put `MESSAGE_CLAIM_DATABASE` on shared persistent storage and set a unique `MESSAGE_CLAIM_INSTANCE_ID` on each instance. The SQLite lease prevents duplicate message processing and allows another instance to retry an expired claim.

## Cloud deployment notes

On cloud hosts (Railway, Render), use `/data/` paths and mount a persistent volume to `/data`. Without a persistent volume, file changes do not survive redeployment.
