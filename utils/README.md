# utils/

Logic modules for Freesona. All cogs import from here; cogs do not import from each other directly.

| Module | Responsibility |
| :--- | :--- |
| `generation.py` | Gemini API calls, `ConversationResponse`, `safe_generate`, `send_response`, multimodal attachment handling, injection pre/post-check wiring |
| `memory.py` | Long-term per-user fact storage (SQLite); per-channel interaction ID store for Gemini server-side conversation continuity |
| `persona.py` | Persona data layer, structured field assembly, `/setpersona` modal panel, profile save/load |
| `intent.py` | Confidence-scored intent evaluator for autonomy — signal scoring, threshold mapping, `IntentResult` type |
| `security.py` | SSRF URL guard, prompt injection detection and redaction, output safety check, math AST allowlist helpers |
| `search.py` | Web search via Gemini grounding with optional legacy Google Custom Search fallback |
| `config.py` | Config I/O (`config.json`), `embed_footer` helper, provider/model name accessors |
| `rss.py` | RSS/Atom XML parser, feed CRUD, seen-link deduplication tracking |
| `modules.py` | Cog registry — `OPTIONAL_MODULES`, `CORE_EXTENSIONS`, `load_enabled_modules`, `module_extension` |
| `roles.py` | Message author role resolution (user vs. bot vs. webhook) for generation payloads |
| `anniversaries_db.py` | Anniversary event storage and scheduling helpers |

See [docs/architecture.md](../docs/architecture.md) for a full system walkthrough.
