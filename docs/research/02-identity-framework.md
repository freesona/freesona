# Identity Framework

This document follows ASD-STE100 Simplified Technical English.

> "Freesona is a self-hosted AI framework, not merely an AI Discord bot."

## Purpose

This document defines the identity of the Freesona project.

A clear identity guides technical decisions, documentation, release planning, and community expectations.

---

## What Freesona Is

Freesona is:

- self-hosted
- modular
- provider-agnostic ([03-provider-independence.md](./03-provider-independence.md))
- extensible
- architecture-driven ([01-architecture-philosophy.md](./01-architecture-philosophy.md))

It provides infrastructure for building AI-powered Discord experiences rather than a single fixed chatbot.

---

## What Freesona Is Not

Freesona is not intended to be:

- tied to one AI provider
- dependent on one memory backend
- dependent on cloud infrastructure
- a collection of unrelated commands
- feature-driven without architectural direction

---

## Intended Audience

The project primarily targets:

## Self-hosters

Users who want control over their infrastructure and providers.

## Developers

People interested in extending the framework.

## Contributors

Developers improving architecture, providers, documentation, or features.

---

## Architectural Identity

Several characteristics distinguish Freesona.

## Provider Independence

No provider is treated as "first-class."

Every supported provider should integrate through the same abstraction.

---

## Optional Infrastructure

Advanced systems such as ChromaDB should remain optional.

Core functionality should not require external services beyond what is necessary.

---

## Extensibility

Features should integrate naturally into existing architecture rather than introducing special cases.

New providers, cogs, and capabilities should fit established interfaces.

---

## AI-assisted Development

AI is used as an implementation tool.

Architectural ownership remains human.

Typical workflow:

1. Define requirements
2. Design architecture
3. Research documentation
4. Use AI to assist implementation
5. Verify output
6. Test thoroughly
7. Review manually
8. Merge

This keeps architectural decisions intentional while benefiting from AI-assisted development.

---

## Community Philosophy

Contributors should first become users.

Typical progression:

```text
User
 ↓
Bug Reporter
 ↓
Contributor
 ↓
Regular Contributor
 ↓
Maintainer
```

Projects grow through consistent stewardship rather than immediate recruitment of maintainers.

---

## Long-term Vision

Freesona aims to become a stable platform rather than an endless stream of new features.

Future releases should expand capabilities while preserving compatibility and architectural consistency wherever practical.

---

## Identity Statement

Freesona is a self-hosted, modular AI framework for Discord with support for multiple providers, optional retrieval and memory systems, extensible cogs, and an architecture designed for long-term maintainability.

---

## Related Research

- Architecture Philosophy ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- Provider Independence ([03-provider-independence.md](./03-provider-independence.md))
- Dogma vs Doctrine ([08-dogma-vs-doctrine.md](./08-dogma-vs-doctrine.md))
- Decalogue ([09-decalogue.md](./09-decalogue.md))
