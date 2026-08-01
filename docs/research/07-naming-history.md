# Naming History

This document follows ASD-STE100 Simplified Technical English.

> "Names should communicate architecture rather than implementation."

## Purpose

This document records notable naming decisions throughout Freesona's development and the reasoning behind them.

Rather than preserving every historical name, it explains the philosophy used when choosing terminology.

---

## Philosophy

Terminology should remain:

- consistent
- descriptive
- architecture-oriented

A single concept should have a single preferred name.

Changing terminology without architectural justification increases documentation and maintenance costs.

---

## Naming Principles

## Prefer Responsibilities

Names should describe what a component is responsible for rather than how it is implemented.

Examples:

- `ConversationManager`
- `ProviderFactory`
- `PromptBuilder`

These names describe roles rather than technologies.

---

## Avoid Vendor Terminology

Provider-specific language should not leak into core architecture.

For example:

Prefer:

- Provider

instead of:

- Gemini backend
- OpenAI backend
- Model service

This keeps the architecture independent from individual vendors.

---

## Consistency

Documentation should use one preferred term for each concept.

Examples include:

- Provider
- Cog
- Persona
- Memory
- Conversation

Avoid alternating between synonymous names throughout the project. :contentReference[oaicite:3]{index=3}

---

## Documentation

Repository documentation serves as the canonical reference for terminology.

Documentation websites should mirror those definitions rather than introduce competing language. :contentReference[oaicite:4]{index=4}

---

## Evolution

As Freesona matured, naming decisions increasingly reflected architectural responsibilities instead of implementation details.

This reduced ambiguity for contributors and improved long-term maintainability.

---

## Related Research

- Documentation Style Guide
- Architecture Philosophy ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- Identity Framework ([02-identity-framework.md](./02-identity-framework.md))
- Dogma vs Doctrine ([08-dogma-vs-doctrine.md](./08-dogma-vs-doctrine.md))
