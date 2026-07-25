# `utils/`

The `utils/` directory contains shared Freesona logic. Cogs import modules
from this directory. Cogs do not import other cogs directly.

| Module | Responsibility |
|---|---|
| `generation.py` | Generates responses, handles attachments, and injects prompts without provider-specific behavior. |
| `memory.py` | Stores long-term user facts in SQLite. It also stores scoped Gemini interaction continuity. |
| `persona.py` | Manages persona data, structured fields, the `/setpersona` panel, and saved profiles. |
| `intent.py` | Scores autonomy signals, maps scores to thresholds, and defines `IntentResult`. |
| `security.py` | Checks URLs for SSRF, detects and redacts prompt injection, checks output safety, and validates math ASTs. |
| `search.py` | Searches the web with Gemini grounding. It can use Google Custom Search as a legacy fallback. |
| `config.py` | Reads and writes `config.json`. It also provides `embed_footer` and provider/model name accessors. |
| `rss.py` | Parses RSS and Atom XML, manages feeds, and tracks seen links. |
| `modules.py` | Defines the cog registry and manages optional modules. |
| `roles.py` | Resolves a message author as a user, bot, or webhook. |
| `anniversaries_db.py` | Stores anniversary events and provides scheduling helpers. |

See [the architecture guide](../docs/architecture.md) for the system design.
