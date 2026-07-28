# Command Reference

Default prefix is `~`. Change it with `~prefix <symbol>`. Most commands work as both prefix and slash commands. `/setpersona` and `/autonomy` are slash-only because they use Discord UI interactions.

## AI Commands

AI commands are organized by command type in dedicated AI cog modules (`genai_generation`, `genai_persona`, `genai_memory`, `genai_channel`, `genai_autonomy`) and loaded through the aggregate `cogs.ai.genai` extension.

| Command                                                   | Action                                                                                        | Permissions   |
|:----------------------------------------------------------|:----------------------------------------------------------------------------------------------|:--------------|
| `~write <prompt>` (`/write`, alias `~w`)                  | Structured output using active persona                                                        | Anyone        |
| `~ask <question>` (`/ask`, alias `~a`)                    | Conversational response using active persona                                                  | Anyone        |
| `~search <query>` (`/search`, alias `~s`)                 | Web search with AI summary                                                                    | Anyone        |
| `~separate <url>` (`/separate`, aliases `~sep`, `~stems`) | Vocal/instrumental separation via MVSEP                                                       | Anyone        |
| `/kbsearch <query>`                                       | Search the local ChromaDB knowledge base                                                      | Anyone        |
| `/kbadd <title> [content] [attachment]`                   | Add text or a PDF/EPUB/TXT/JSON attachment to the local knowledge base (opens metadata modal) | Administrator |
| `/kblist`                                                 | List the newest knowledge base entries                                                        | Administrator |
| `/kbdelete <id>`                                          | Delete a knowledge base entry by ID                                                           | Administrator |
| `/kbpersona <persona> [limit]`                            | List all knowledge entries for a specific persona                                             | Administrator |

---

### `/kbadd` Metadata Fields

The `/kbadd` command opens a modal with the following fields:

**Required:**
| Field | Description | Example |

|-------|-------------|---------|
| Persona ID | Persona identifier | `chisato_nishikigi` |
| Source | Original source reference | `Episode 06` |
| Source Type | `anime`, `novel`, `manga`, `game`, `guidebook`, `interview`, `website`, `other` | `anime` |
| Entry Type | `dialogue`, `narration`, `event`, `relationship`, `description` | `dialogue` |
| Topics | Comma-separated semantic topics | `friendship, optimism, coffee` |

**Optional:**
| Field | Description | Example |

|-------|-------------|---------|
| Scene | Scene/location description | `Aquarium visit` |
| Speaker | Speaking character (auto-sets entry_type to dialogue) | `Chisato` |
| Episode | Episode number | `06` |
| Chapter | Chapter number/title | `Chapter 12` |
| Timestamp | Source timestamp | `2023-01-15` or `S01E06 12:34` |
| Canon Level | `canon`, `semi-canon`, `non-canon`, `headcanon`, `alternate` | `canon` |
| Tags | Comma-separated additional tags | `canon, emotional, key_moment` |

---

## RSS / News

| Command                      | Action                                          | Permissions   |
|:-----------------------------|:------------------------------------------------|:--------------|
| `/rss latest <feed>`         | Show latest items from an RSS/Atom feed         | Anyone        |
| `/rss list`                  | List configured RSS feeds and auto-post channel | Anyone        |
| `/rss add <name> <url>`      | Add or update an RSS feed                       | Administrator |
| `/rss remove <name>`         | Remove an RSS feed                              | Administrator |
| `/rss setchannel <#channel>` | Set RSS auto-post channel                       | Administrator |
| `/rss clearchannel`          | Disable RSS auto-posting                        | Administrator |

## Conversation Channel

| Command                          | Action                                                  | Permissions   |
|:---------------------------------|:--------------------------------------------------------|:--------------|
| `/setchannel #channel`           | Set the AI conversation channel                         | Administrator |
| `/clearchannel`                  | Remove the conversation channel                         | Administrator |
| `/clearmemory`                   | Clear server-side conversation history for this channel | Administrator |
| `/chatmode <all/mentions/smart>` | Set when the bot replies in the conversation channel    | Administrator |

The bot responds to messages in the configured conversation channel. `all` replies to every message; `mentions` replies only to direct mentions and replies to the bot; `smart` also responds to messages with attachments.

## Persona & Memory

| Command                                                           | Action                                                                 | Permissions                |
|:------------------------------------------------------------------|:-----------------------------------------------------------------------|:---------------------------|
| `/setpersona`                                                     | Open the button-based persona editor                                   | Bot Owner                  |
| `/personalock` (`~personalock`, alias `~plock`)                   | Lock persona against changes                                           | Bot Owner                  |
| `/personaunlock` (`~personaunlock`, alias `~pulock`)              | Unlock persona                                                         | Bot Owner                  |
| `/personasave <name>` (`~personasave`, alias `~psave`)            | Save current persona as a preset                                       | Bot Owner                  |
| `/personaload <name>` (`~personaload`, alias `~pload`)            | Load a saved persona preset                                            | Bot Owner                  |
| `/personalist` (`~personalist`, alias `~plist`)                   | List saved persona presets                                             | Bot Owner                  |
| `/personadelete <name>` (`~personadelete`, alias `~pdel`)         | Delete a saved persona preset                                          | Bot Owner                  |
| `/debugpersona` (`~debugpersona`, alias `~pdeb`)                  | Show active persona, last prompt, provider/model, lock state, autonomy | Bot Owner                  |
| `/personareload` (`~personareload`, alias `~preload`)             | Reload persona from JSON file without rebooting                        | Bot Owner                  |
| `/memorylist [user]` (`~memorylist`, alias `~meml`)               | List long-term memory facts for a user                                 | User (own) / Administrator |
| `/memoryclear [user]` (`~memoryclear`, alias `~memcl`)            | Clear long-term memory facts for a user                                | User (own) / Administrator |
| `/memorydelete <index> [user]` (`~memorydelete`, alias `~memdel`) | Delete a specific memory fact by list number                           | User (own) / Administrator |
| `/migrate` (`~migrate`)                                           | Migrate legacy JSON memory to SQLite                                   | Administrator              |

## Runtime Controls

| Command                                        | Action                                                                                       | Permissions   |
|:-----------------------------------------------|:---------------------------------------------------------------------------------------------|:--------------|
| `/module list`                                 | List enabled/disabled modules with load state                                                | Administrator |
| `/module enable <name>`                        | Enable and load a module                                                                     | Administrator |
| `/module disable <name>`                       | Disable and unload a module                                                                  | Administrator |
| `/module reload <name>`                        | Reload an enabled module                                                                     | Administrator |
| `/model show`                                  | Show the active model                                                                        | Bot Owner     |
| `/model set <name>`                            | Set the active model                                                                         | Bot Owner     |
| `/model reset`                                 | Reset to the environment/default model                                                       | Bot Owner     |
| `/provider show`                               | Show the active AI provider                                                                  | Bot Owner     |
| `/provider set <name>`                         | Set the active provider (`gemini`, `openai`, `ollama`, `nim`, `azure`, `groq`, `openrouter`) | Bot Owner     |
| `/provider reset`                              | Reset provider to the environment/default                                                    | Bot Owner     |
| `/botwhitelist` (`~botwhitelist`, alias `~bw`) | List whitelisted bot IDs                                                                     | Administrator |
| `/botwhitelist add <bot_id>`                   | Add a bot ID (integer snowflake) to the whitelist                                            | Administrator |
| `/botwhitelist remove <bot_id>`                | Remove a bot ID from the whitelist                                                           | Administrator |
| `/sync`                                        | Sync global slash commands                                                                   | Bot Owner     |
| `/dumpconfig`                                  | Dump current `config.json` contents                                                          | Bot Owner     |
| `/reboot`                                      | Gracefully shutdown the bot for restart (Owner only). Requires process manager to restart.   | Bot Owner     |
| `/config show [key]`                           | Show all runtime config values, or a specific key                                            | Bot Owner     |
| `/config list`                                 | List all configurable keys with descriptions                                                 | Bot Owner     |
| `/config set <key> <value>`                    | Set a config value (type-converted)                                                          | Bot Owner     |
| `/config reset <key>`                          | Reset a config key to its default value                                                      | Bot Owner     |
| `/settimezone <timezone>`                      | Set the bot's timezone (IANA format, e.g. `Asia/Manila`)                                     | Administrator |
| `/timezone`                                    | Show the bot's currently configured timezone                                                 | Anyone        |

Module and model names include slash-command autocomplete suggestions.

## Autonomy

| Command                                  | Action                   | Permissions   |
|:-----------------------------------------|:-------------------------|:--------------|
| `/autonomy on`                           | Enable autonomous mode   | Administrator |
| `/autonomy off`                          | Disable autonomous mode  | Administrator |
| `/autonomy frequency <low/default/high>` | Set confidence threshold | Administrator |

Autonomous mode uses a confidence-scored intent evaluator (not random chance). Thresholds: `low` = 0.70, `default` = 0.50, `high` = 0.35. A 120-second per-channel cooldown and 60-second per-user cooldown prevent the bot from dominating a conversation.

## Moderation

| Command                                         | Action                                                      | Permissions      |
|:------------------------------------------------|:------------------------------------------------------------|:-----------------|
| `~purge <limit>`                                | Delete messages (1–1000)                                    | Manage Messages  |
| `~kick <member> [reason]`                       | Kick a member                                               | Kick Members     |
| `~ban <user> [delete_messages] [reason]`        | Ban a user; optionally delete message history (e.g. `7d`)   | Ban Members      |
| `~softban <member> [delete_messages] [reason]`  | Ban and immediately unban to purge messages (default: `7d`) | Ban Members      |
| `~unban <user> [reason]`                        | Unban a user                                                | Ban Members      |
| `~timeout <member> <duration> [reason]` (`~to`) | Timeout a member (e.g. `10m`, `1h`)                         | Moderate Members |
| `~removetimeout <member>` (`~rt`, `~rto`)       | Remove a timeout                                            | Moderate Members |
| `~slowmode <duration\|off>`                     | Set slowmode delay for the current channel                  | Manage Channels  |
| `~lock [reason]`                                | Lock the current channel                                    | Manage Channels  |
| `~unlock [reason]`                              | Unlock the current channel                                  | Manage Channels  |
| `~warn <member\|id> [reason]`                   | Issue a warning with a unique hex ID                        | Moderate Members |
| `~warns <member\|id>`                           | Show all warnings for a member                              | Moderate Members |
| `~delwarn <warn_id>`                            | Delete a warning by its hex ID                              | Moderate Members |
| `~clearwarns <member\|id>`                      | Clear all warnings for a member                             | Moderate Members |
| `~warnthresholds` (`~wt`)                       | View or edit auto-punishment thresholds via modal           | Administrator    |

Warn thresholds support `timeout <duration>`, `kick`, and `ban` actions triggered at configurable warning counts. Configured via `/warnthresholds` modal (slash command only).

## Utility & Fun

| Command                         | Action                                              | Permissions      |
|:--------------------------------|:----------------------------------------------------|:-----------------|
| `~help [command]`               | Show help for commands                              | Anyone           |
| `~prefix <symbol>`              | Change command prefix                               | Administrator    |
| `~math <equation>`              | Solve an equation via Wolfram\|Alpha                | Anyone           |
| `~plot <function>`              | Generate a 2D plot of a mathematical function       | Anyone           |
| `~download <url>` (`~dl`)       | Download a video (1080p → 720p → 480p → compressed) | Anyone           |
| `~audio <url>` (`~mp3`)         | Download audio as MP3                               | Anyone           |
| `~ping`                         | Show bot and Discord API latency                    | Anyone           |
| `~hello`                        | Say hello back                                      | Anyone           |
| `~randommember`                 | Randomly select a server member                     | Mention Everyone |
| `~coinflip`                     | Flip a coin                                         | Anyone           |
| `~roll [sides]`                 | Roll a die (default: 6 sides)                       | Anyone           |
| `~pick <choice1, choice2, ...>` | Pick randomly from comma-separated choices          | Anyone           |
