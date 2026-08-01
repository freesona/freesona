# Architecture Philosophy

This document follows ASD-STE100 Simplified Technical English.

> "Architecture should outlive implementations."

## Purpose

This document explains the architectural principles that guide Freesona. It is not an implementation guide. Instead, it documents the reasoning behind the project's structure so future contributors understand *why* components are organized the way they are.

---

## Goals

The primary architectural goals are:

- Provider independence ([03-provider-independence.md](./03-provider-independence.md))
- Separation of concerns ([08-dogma-vs-doctrine.md](./08-dogma-vs-doctrine.md))
- Extensibility
- Optional components ([08-dogma-vs-doctrine.md](./08-dogma-vs-doctrine.md))
- Maintainability
- Long-term stability

Features should support these goals rather than compromise them.

---

## Freesona is a Framework

Although Freesona originated as a Discord bot, its architecture intentionally treats Discord as one interface rather than the application itself.

Core responsibilities are isolated from Discord-specific code wherever practical.

Examples include:

- AI generation
- Memory
- Provider selection
- Configuration
- Prompt construction

Discord cogs act primarily as adapters between Discord interactions and reusable application logic.

---

## Separation of Concerns

Responsibilities should have clear ownership.

```text
Discord
     │
     ▼
Cogs
     │
     ▼
Generation Pipeline
     │
     ├──────── Memory
     ├──────── Providers
     ├──────── Prompt Builder
     └──────── Configuration
```

Business logic belongs in reusable modules.

Discord-specific behavior belongs in cogs.

Avoid placing provider-specific code inside Discord commands.

---

## Provider Independence

No AI provider should become the center of the architecture.

Providers are implementation details behind a common interface.

This allows:

- Gemini
- OpenAI
- Ollama
- Groq
- OpenRouter
- Azure
- NVIDIA NIM

to coexist without changing command implementations.

Adding a provider should require minimal architectural changes.

---

## Optional Components

Optional features should remain optional.

Examples include:

- ChromaDB
- Long-term memory
- Retrieval-Augmented Generation

Users should not be forced to install infrastructure they do not intend to use.

Optional dependencies reduce barriers to adoption while keeping advanced functionality available.

---

## Documentation as Architecture

Documentation is considered part of the architecture rather than an afterthought.

Canonical documentation resides in `docs/`.

Documentation should explain:

- what exists
- why it exists
- how components interact

rather than merely describing implementation.

---

## Stability Before Features

A stable architecture is more valuable than an ever-growing feature list.

A release should be considered complete when:

- architecture is coherent
- providers behave consistently
- documentation matches implementation
- setup is reliable
- testing demonstrates stability

rather than when every desired feature has been implemented.

---

## Framework Philosophy

The long-term objective is not to become "the Discord bot with the most features."

Instead:

- provide a stable foundation
- make extension straightforward
- keep responsibilities isolated
- minimize vendor lock-in
- support future evolution without redesign

---

## Related Research

- Identity Framework ([02-identity-framework.md](./02-identity-framework.md))
- Provider Independence ([03-provider-independence.md](./03-provider-independence.md))
- PromptBuilder ([04-promptbuilder.md](./04-promptbuilder.md))
- Character Memory ([05-character-memory.md](./05-character-memory.md))
- Rejected Ideas ([10-rejected-ideas.md](./10-rejected-ideas.md))
- Dogma vs Doctrine ([08-dogma-vs-doctrine.md](./08-dogma-vs-doctrine.md))
- Decalogue ([09-decalogue.md](./09-decalogue.md))
