---
name: freesona-discord
description: Rules for modifying Freesona's Discord integration layer.
---
# Freesona Discord Integration

This skill governs your changes to how Freesona implements `discord.py`. Inspect the `dev` branch to verify your integration architecture before you make changes.

## Your Inspection Requirements
Before you modify Discord code, locate:
- Your active Cog and module structure.
- How your system loads extensions during initialization.
- The organization of your commands and event listeners.
- Any optional modules or specific Discord boundaries.
- How Discord IDs (user, guild, channel) map to your internal Freesona data structures.
- How Discord events trigger updates to your conversation state and user memory.
- Relevant tests.

## Strict Boundaries
- **Core Logic:** Keep your core Freesona logic out of Discord Cogs. Your Discord layer should only handle API events and pass data to internal managers.
- **Library Reference:** Use the `discord-py` skill for your library-specific syntax. This skill only covers your specific implementation of the library.

## Modification Rules
- Maintain the existing separation between your bot interface and core processing.
- Verify your interaction and command behavior against existing tests.
