# Dogma vs Doctrine

This document follows ASD-STE100 Simplified Technical English.

> "Architectural principles should guide decisions, not prevent evolution."

## Purpose

This document distinguishes between immutable architectural principles (dogma) and implementation guidance (doctrine).

Understanding the difference helps contributors know which decisions require architectural discussion and which can evolve naturally over time.

---

## Definitions

## Dogma

Dogma consists of principles that define Freesona's architectural identity.

Changing them fundamentally changes the project.

Examples include:

- Provider independence ([03-provider-independence.md](./03-provider-independence.md))
- Separation of concerns ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- Modular architecture
- Canonical documentation
- Optional infrastructure ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- Human architectural ownership

These principles should change only through deliberate architectural discussion.

---

## Doctrine

Doctrine consists of recommended implementation practices.

Doctrine evolves as the project grows.

Examples include:

- preferred project layout
- logging conventions
- testing practices
- documentation style
- contributor workflow
- release process

Doctrine should improve over time without requiring architectural redesign.

---

## Why the Distinction Matters

Without this distinction, every coding decision risks becoming an architectural debate.

Likewise, treating architectural principles as optional eventually erodes consistency.

Separating the two provides stability while allowing continuous improvement.

---

## Dogma Should Be Stable

Architectural principles should remain stable across releases.

Examples include:

- providers communicate through common abstractions
- Discord logic remains isolated from reusable logic
- documentation remains part of the architecture
- optional systems remain optional

These principles define Freesona regardless of implementation language or provider ecosystem.

---

## Doctrine Should Evolve

Implementation guidance should respond to experience.

Examples include:

- improving contributor documentation
- refining testing requirements
- changing formatting tools
- updating release workflows
- improving setup scripts

These changes improve development without redefining the project.

---

## Decision Framework

When proposing a change, ask:

Does this change architecture?

If yes:

- discuss first
- reach consensus
- document the reasoning

If no:

- implement
- review
- iterate

---

## Long-term Vision

Dogma preserves Freesona's identity.

Doctrine improves how that identity is implemented.

Both are necessary for sustainable development.

---

## Related Research

- Architecture Philosophy ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- Decalogue ([09-decalogue.md](./09-decalogue.md))
- Identity Framework ([02-identity-framework.md](./02-identity-framework.md))
- Provider Independence ([03-provider-independence.md](./03-provider-independence.md))
- bee0d54 Retrospective ([06-bee0d54-retrospective.md](./06-bee0d54-retrospective.md))
