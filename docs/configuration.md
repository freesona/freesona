# Configuration

This document follows ASD-STE100 Simplified Technical English.

This document lists the environment variables used by Freesona. Copy
`.env.sample` to `.env` and set the values for your deployment.

## Required variables

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `BOT_TOKEN` | Discord bot token | `MTIz...` |
| `CHANNEL_ID` | Discord channel ID for the startup message | `123456789` |

Set credentials for the selected AI provider. For example, Gemini needs
`GOOGLE_API_KEY`, which is also used by web search. `AI_PROVIDER` defaults to
`gemini`; it is not required. Ollama does not need a provider API key.

## AI Provider variables

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `AI_PROVIDER` | Provider name: `gemini`, `openai`, `ollama`, `nim`, `azure`, `groq`, `openrouter`, `custom` | `gemini` |
| `AI_PROVIDER_MODEL` | Override the configured provider model | `gemini-2.5-flash` |
| `MODEL_NAME` | Default model name | `gemini-flash-lite-latest` |
| `MODEL_TEMPERATURE` | Model temperature 0.0-2.0 | `0.7` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `OLLAMA_BASE_URL` | Ollama base URL | `http://localhost:11434/api/chat` |
| `NVIDIA_API_KEY` or `NIM_API_KEY` | NVIDIA NIM API key | `nvapi-...` |
| `NVIDIA_NIM_BASE_URL` | NVIDIA NIM base URL | `https://integrate.api.nvidia.com/v1/chat/completions` |
| `NIM_BASE_URL` | Alias for `NVIDIA_NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1/chat/completions` |
| `AZURE_AI_KEY` | Azure AI Foundry key | `...` |
| `GROQ_API_KEY` | Groq API key | `gsk_...` |
| `OPENROUTER_API_KEY` | OpenRouter API key | `sk-or-...` |
| `OPENROUTER_SITE_URL` | OpenRouter site URL | `https://example.com` |
| `OPENROUTER_SITE_NAME` | OpenRouter site name | `Freesona` |
| `CUSTOM_API_BASE_URL` | OpenAI-compatible chat-completions URL | `http://localhost:8000/v1/chat/completions` |
| `CUSTOM_API_KEY` | Custom API key (optional) | `...` |

The OpenAI and Azure provider URLs are set in the provider implementation.
`OPENAI_BASE_URL` and `AZURE_AI_BASE_URL` are not read as environment
variables. The Azure provider currently uses a code-defined placeholder URL;
it does not read your Azure AI Foundry endpoint.

## Application and knowledge base

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `BOT_NAME` | Name shown in messages and startup notices | `Freesona` |
| `AI_PERSONA` | Fallback persona text when no persona file is available | `You are a helpful assistant.` |
| `KB_ENABLED` | Enable knowledge base retrieval (`true` or `false`) | `true` |
| `KB_TOP_K` | Maximum knowledge entries retrieved for a response | `5` |
| `KNOWLEDGE_BASE_DATABASE` | SQLite database for knowledge base entries | `knowledge.db` |
| `DEFAULT_PERSONA_ID` | Persona ID pre-filled by `/kbadd` when none is provided (unset leaves the field blank) | `persona` |
| `EMBEDDING_MODEL` | Embedding model label added to knowledge metadata | `text-embedding-3-large` |
| `LEGACY_PATH` | Legacy JSON memory file used by the migration command | `memory.json` |

## ChromaDB variables

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `CHROMA_COLLECTION` | ChromaDB collection name | `freesona` |
| `CHROMA_PERSIST_DIRECTORY` | ChromaDB persist directory | `./.chroma` |

## FastAPI administration

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `HTTP_PORT` | HTTP server port | `10000` |
| `ADMIN_API_TOKEN` | Bearer token for admin routes | `use-a-long-random-secret` |

## Multi-instance message claiming

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `MESSAGE_CLAIM_DATABASE` | Database for message leases | `memory.db` |
| `MESSAGE_CLAIM_INSTANCE_ID` | Unique instance ID | `instance-1` |
| `MESSAGE_CLAIM_LEASE_SECONDS` | Lease duration in seconds | `300` |

## Optional integrations

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `MVSEP_API_KEY` | MVSEP API key | `...` |
| `MVSEP_WEBHOOK_URL` | MVSEP webhook URL | `https://host.example.com/webhooks/mvsep` |
| `MVSEP_WEBHOOK_SEND_MAIL_ON_ERROR` | Send mail on error | `false` |
| `WOLFRAM_APPID_SHORT` | Wolfram Alpha short app ID | `...` |
| `WOLFRAM_APPID_LLM` | Wolfram Alpha LLM app ID | `...` |
| `DELPHITOOLS_EXECUTABLE` | Delphitools executable name or full path | `dt` |

Set `DELPHITOOLS_EXECUTABLE` to the full executable path when the bot runs with
a different `PATH` than your interactive shell.

## File path variables

| Variable | Description | Local example | Cloud example |
| :------- | :---------- | :------------ | :------------ |
| `AI_PERSONA_FILE` | Persona text file | `persona.txt` | `/data/persona.txt` |
| `AI_PERSONA_JSON_FILE` | Persona JSON file | `persona.json` | `/data/persona.json` |
| `AI_PERSONAS_FILE` | Personas presets file | `personas.json` | `/data/personas.json` |
| `CONFIG_FILE_PATH` | Config file path | `config.json` | `/data/config.json` |
| `MEMORY_FILE_PATH` | Memory database | `memory.db` | `/data/memory.db` |
| `WARNINGS_FILE_PATH` | Warnings database | `warnings.db` | `/data/warnings.db` |
| `ANNIVERSARIES_FILE_PATH` | Anniversaries database | `anniversaries.db` | `/data/anniversaries.db` |
| `CANON_FILE_PATH` | Canon database | `canon.db` | `/data/canon.db` |
| `CHARACTER_MEMORY_FILE_PATH` | Character memory database | `character_memory.db` | `/data/character_memory.db` |

On cloud hosts (Railway, Render), use `/data/` paths and mount a persistent volume to `/data`. Without a persistent volume, file changes do not survive redeployment.

## Logging variables

| Variable | Description | Example |
| :------- | :---------- | :------ |
| `LOG_ENABLED` | Enable optional logging | `false` |
| `LOG_CHANNEL_ID` | Discord channel for log messages | `123456789` |
| `LOG_LEVEL` | Log level | `INFO` |
| `LOG_FILE_PATH` | Log file path | `logs/freesona.log` |
| `LOG_FILE_MAX_MONTHS` | Log rotation period in months | `3` |
| `LOG_INCLUDE_DISCORD` | Send logs to Discord channel | `true` |
| `LOG_SECTION_GENERAL` | Log general bot events | `true` |
| `LOG_SECTION_CONFIG` | Log configuration changes | `false` |
| `LOG_SECTION_AI` | Log AI provider calls | `true` |
| `LOG_SECTION_MEMORY` | Log memory operations | `false` |
| `LOG_SECTION_MEDIA` | Log media operations | `false` |
| `LOG_SECTION_MODERATION` | Log moderation actions | `false` |
| `LOG_SECTION_SECURITY` | Log security checks | `true` |
| `LOG_SECTION_WEBHOOK` | Log webhook events | `false` |
