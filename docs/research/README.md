# Research

This document follows ASD-STE100 Simplified Technical English.

This directory preserves the architectural history and design rationale behind Freesona.

Unlike the documentation in the mainline `docs/`, these documents are not user guides or API references. They exist to explain **why** Freesona was designed the way it is, record major architectural decisions, and preserve historical context that may otherwise be lost over time.

These documents are intended primarily for maintainers, contributors, and anyone interested in understanding the project's evolution.

---

## Structure

The research library is divided into two categories.

### Canonical Architecture

These documents describe the architectural principles that define Freesona. They should evolve alongside the project as the architecture changes.

| Document                        | Purpose                                                                             |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| `01-Architecture-Philosophy.md` | Core architectural principles and long-term design goals.                           |
| `02-Identity-Framework.md`      | Defines what Freesona is, its intended scope, and project identity.                 |
| `03-Provider-Independence.md`   | Explains the provider abstraction and the rationale behind avoiding vendor lock-in. |
| `04-PromptBuilder.md`           | Documents the architectural vision for prompt construction.                         |
| `05-Character-Memory.md`        | Describes the long-term direction for persistent character memory.                  |

---

### Historical & Governance

These documents preserve the reasoning behind important decisions, project history, and governance philosophy. They serve as institutional memory and should change infrequently.

| Document                      | Purpose                                                                                         |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `06-bee0d54-Retrospective.md` | Lessons learned during a major architectural milestone.                                         |
| `07-Naming-History.md`        | Records terminology and naming decisions throughout the project's history.                      |
| `08-Dogma-vs-Doctrine.md`     | Distinguishes immutable architectural principles from evolving implementation practices.        |
| `09-Decalogue.md`             | Summarizes the project's ten guiding architectural principles.                                  |
| `10-Rejected-Ideas.md`        | Records ideas that were postponed or rejected, along with the reasoning behind those decisions. |

---

## Relationship to `docs/`

This directory complements, but does not replace, the project's documentation.

* `docs/` explains **how** Freesona works.
* `research/` explains **why** it was designed that way.

Whenever possible, implementation details should remain in `docs/`, while architectural reasoning belongs here.

---

## Intended Audience

This research library is written primarily for:

* Project maintainers
* Contributors
* Future maintainers
* Anyone interested in the architectural evolution of Freesona

It is not required reading for users who simply want to install or use the project.

---

## Status

These documents are living records.

They may be revised as Freesona evolves, but historical context should be preserved whenever practical. Significant architectural changes should update the relevant research document so future contributors can understand both the decision and its rationale.

---

## Guiding Principle

Architecture is more than code.

This directory exists to preserve the decisions, trade-offs, and philosophy that shaped Freesona, ensuring they remain understandable long after the original implementation has changed.
