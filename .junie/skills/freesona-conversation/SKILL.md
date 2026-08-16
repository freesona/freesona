---
name: freesona-conversation
description: Rules for modifying Freesona's short-term conversation state.
---
# Freesona Conversation State

This skill governs your changes to short-term conversational context. Verify your `dev` branch implementation before you alter state management.

## Your Inspection Requirements
Before you modify conversation code, inspect the repository to find:
- Your `ConversationManager` or equivalent component.
- Your state scope and identifier rules (user, guild, channel).
- Message storage formats.
- Your token budgets and maximum history limits.
- Context assembly methods.
- Concurrency and async handling.
- TTL and cleanup logic.
- Relevant tests.

## Strict Boundaries
- **Persistent Memory:** Do not move persistent facts into your conversation state.
- **Architecture Changes:** Do not move persistent facts into conversation state or vice versa unless the task explicitly requires it.

## Modification Rules
- Respect the existing boundaries for your short-term state.
- Keep your token tracking and cleanup rules intact.
