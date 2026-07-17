# AGENTS.md

> Guidance for AI assistants and human contributors working on the Freesona codebase.

---

# Overview

Freesona is a self-hosted, modular Discord AI framework designed around provider abstraction, extensibility, and maintainability.

The project supports multiple AI providers while presenting a unified interface to the rest of the application. Features should remain provider-agnostic whenever practical.

This document defines architectural expectations for AI assistants contributing code.

---

# Core Principles

## Architecture First

Do not begin implementation before understanding the existing architecture.

When introducing a new feature:

1. Identify where it belongs.
2. Reuse existing abstractions.
3. Extend existing systems before introducing new ones.

Avoid duplicate implementations.

---

## Provider Independence

The rest of Freesona should not depend on provider-specific behavior.

Provider implementations should remain isolated behind common interfaces.

Avoid code such as:

```python
if provider == "gemini":
```

inside shared application logic.

Instead, encapsulate provider-specific behavior within provider modules.

---

## Separation of Concerns

Each module should have one primary responsibility.

Examples:

| Component    | Responsibility                    |
| ------------ | --------------------------------- |
| `cogs/`      | Discord interactions              |
| `utils/`     | Shared application logic          |
| `providers/` | AI provider implementations       |
| `memory/`    | Conversation and long-term memory |
| `scripts/`   | Development utilities             |
| `docs/`      | Canonical documentation           |

Business logic should never be tightly coupled to Discord-specific code.

---

# Before Writing Code

Always determine whether an existing solution already exists.

Before introducing:

* a helper function,
* utility,
* abstraction,
* service,
* model,

search the project for an existing implementation.

Prefer extending existing code over creating parallel systems.

---

# Backwards Compatibility

Avoid unnecessary breaking changes.

If an existing interface must change:

* update documentation,
* update tests,
* preserve compatibility whenever practical.

Breaking changes should be intentional rather than incidental.

---

# Code Style

Prioritize:

* readability,
* maintainability,
* explicit behavior.

Avoid overly clever implementations.

Readable code is preferred over shorter code.

---

# Type Hints

Use type hints whenever practical.

New public interfaces should include appropriate typing.

---

# Error Handling

Never silently ignore exceptions.

Avoid:

```python
except:
    pass
```

Instead:

* catch specific exceptions,
* provide meaningful error messages,
* log unexpected failures.

---

# Logging

Use the project's logging framework.

Do not introduce `print()` statements for diagnostics.

Log messages should provide actionable information.

---

# Documentation

Documentation is part of the implementation.

Whenever behavior changes:

* update relevant documentation,
* update examples,
* update configuration references,
* ensure documentation matches implementation.

The repository's `docs/` directory is the canonical source of documentation.

---

# Configuration

Configuration belongs in:

* `.env`
* configuration modules
* documented defaults

Do not hardcode:

* API keys,
* IDs,
* provider URLs,
* user-specific configuration.

Any new configuration option must also update:

* `.env.sample`
* documentation

---

# AI Providers

All providers should expose equivalent behavior through a common interface.

Provider implementations should remain stateless whenever practical.

Conversation management, personas, and memory belong to Freesona—not individual providers.

---

# Memory Systems

Treat the following as separate systems:

## Conversation Memory

Short-term context for the active conversation.

---

## Long-Term Memory

Persistent information retained across conversations.

---

## Persona Knowledge

Canonical information describing a persona.

---

## Retrieval (RAG)

Retrieves relevant knowledge to support generation.

Do not combine these systems into a single implementation.

Each exists for a different purpose.

---

# Performance

Optimize only after identifying measurable bottlenecks.

Avoid premature optimization.

Typical priorities:

1. Correctness
2. Maintainability
3. Performance

---

# Security

Never introduce:

* embedded secrets,
* hardcoded credentials,
* unsafe shell execution,
* arbitrary code execution,
* unsafe deserialization.

Validate external input whenever practical.

---

# Dependencies

Before adding a dependency:

* determine whether the standard library is sufficient,
* justify the dependency,
* keep the dependency footprint minimal.

Avoid adding libraries for trivial functionality.

---

# Testing

New functionality should include tests whenever practical.

Bug fixes should include regression tests when feasible.

Do not modify tests solely to make failing code pass.

---

# Documentation Style

Documentation should:

* explain **why** before **how**,
* avoid marketing language,
* remain technically accurate,
* assume the reader is unfamiliar with Freesona.

---

# Design Philosophy

Favor:

* modularity,
* composition,
* explicit interfaces,
* provider abstraction,
* predictable behavior.

Avoid tightly coupling unrelated systems.

---

# Feature Scope

Freesona is an AI framework first.

Features should strengthen that goal.

Ask before implementing a feature:

* Does it improve the AI experience?
* Does it improve self-hosting?
* Does it improve maintainability?
* Can it remain modular?

Avoid unrelated feature creep.

---

# AI Assistance

AI-generated code is acceptable.

However, generated code is expected to be:

* reviewed,
* understood,
* tested,
* integrated with the existing architecture.

Generated code should never be accepted without verification.

---

# Pull Request Expectations

Contributions should:

* follow existing architecture,
* avoid unnecessary refactoring,
* minimize unrelated changes,
* update documentation when needed,
* preserve project consistency.

Large architectural changes should be discussed before implementation.

---

# Final Guideline

When uncertain, prioritize consistency with the existing architecture over introducing new patterns.

Freesona values long-term maintainability, provider independence, and a clean, modular design above feature count or implementation novelty.
