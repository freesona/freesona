# PromptBuilder

This document follows ASD-STE100 Simplified Technical English.

> "Prompt construction should be explicit, reusable, and independent of providers."

## Purpose

This document describes the architectural vision for a dedicated PromptBuilder within Freesona.

While prompt generation may evolve over time, the guiding principles remain consistent.

---

## Motivation

Prompt construction is one of the most important parts of an AI application.

Without a dedicated abstraction, prompts tend to become:

- duplicated
- provider-specific
- difficult to test
- difficult to extend

Centralizing prompt construction improves consistency across every provider.

---

## Responsibilities

A PromptBuilder should assemble all information required before generation.

Examples include:

- conversation history
- personas
- memories ([05-character-memory.md](./05-character-memory.md))
- retrieved knowledge
- system instructions
- runtime configuration

Its responsibility ends once a complete prompt package has been produced.

Generation itself belongs elsewhere.

---

## Separation of Responsibilities

```text
Discord
    │
    ▼
Cog
    │
    ▼
PromptBuilder
    │
    ▼
Generation
    │
    ▼
Provider
```

Each layer has a single responsibility.

PromptBuilder determines *what* should be sent.

Providers determine *how* it is sent.

---

## Independence

PromptBuilder should remain independent from provider implementations.

It should not contain:

- Gemini-specific formatting
- OpenAI-specific formatting
- Ollama-specific logic

Provider adapters may perform any necessary translation after prompt construction.

---

## Inputs

PromptBuilder may consume information from several sources:

- conversation history
- long-term memory
- retrieved knowledge
- personas
- runtime settings
- user message

Each source contributes context without taking ownership of prompt assembly.

---

## Benefits

A dedicated PromptBuilder improves:

## Consistency

All providers receive prompts built from the same architectural rules.

---

## Testing

Prompt construction becomes independently testable.

Developers can inspect prompts without making API requests.

---

## Maintainability

Prompt improvements occur in one location rather than across multiple providers.

---

## Extensibility

Future features can contribute additional context without modifying every provider implementation.

---

## Design Principles

PromptBuilder should:

- remain deterministic
- avoid network requests
- avoid provider-specific behavior
- produce predictable output
- remain reusable outside Discord

---

## Long-term Vision

PromptBuilder represents the canonical place where Freesona's architectural decisions regarding prompt composition are expressed.

It allows prompt engineering to evolve independently of providers while preserving a stable generation pipeline.

---

## Related Research

- Architecture Philosophy ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- Provider Independence ([03-provider-independence.md](./03-provider-independence.md))
- Character Memory ([05-character-memory.md](./05-character-memory.md))
- Identity Framework ([02-identity-framework.md](./02-identity-framework.md))
