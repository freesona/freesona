# Contributing to Freesona

Thanks for helping improve Freesona. This project is a self-hosted framework for AI-powered characters and personas, and the contribution style should preserve the repository’s architecture and long-term maintainability.

## Project goals

Freesona is built around these principles:

- Provider independence
- Character and persona architecture
- Long-term maintainability
- Research and experimentation

The framework owns conversation management, memory, personas, and application behavior. AI providers are interchangeable components that generate outputs through shared interfaces.

## Before making changes

Please follow these steps before opening a pull request or proposing a new feature:

1. Read the surrounding code and relevant documentation.
2. Search for an existing implementation before introducing a new one.
3. Extend existing abstractions when appropriate.
4. Keep each change focused on one responsibility.
5. Preserve existing behavior unless the change is explicitly intentional.

Prefer improving existing architecture over introducing parallel systems.

## Architecture expectations

Keep responsibilities separated.

- `cogs/` — Discord commands and event handlers
- `utils/` — Shared application logic
- `providers/` — Provider implementations
- `memory/` — Conversation and long-term memory systems
- `scripts/` — Development utilities
- `docs/` — Project documentation

Business logic belongs in shared modules rather than Discord-specific code.

## Provider independence

Provider-specific behavior must remain inside provider modules.

Do not add branching such as:

```python
if provider == "gemini":
```

Instead:

- Extend the provider interface.
- Implement provider-specific behavior in the provider implementation.
- Keep shared application code provider-agnostic.

Providers should remain stateless whenever practical.

Freesona owns the following responsibilities:

- Conversations
- Personas
- Memory
- Prompt construction
- Application state

## Memory architecture

Treat each memory system as an independent responsibility.

- Conversation memory — active conversation context
- Long-term memory — persistent facts and experiences
- Persona knowledge — canonical character information
- Retrieval (RAG) — supporting context for generation

Do not merge these systems into a single implementation.

## Research and experimentation

Research is encouraged, but experimental work should not complicate the core architecture.

When introducing a new design:

- Prefer composition over special cases.
- Validate ideas with measurable benefits.
- Avoid adding abstractions without a clear purpose.
- Keep experiments isolated until proven useful.

## Implementation guidelines

When writing code, prefer:

- Correctness
- Maintainability
- Readability
- Performance after measurement

Please follow these practical expectations:

- Follow PEP 8.
- Keep formatting consistent with the project’s configured formatter and linters.
- Give each module one primary responsibility.
- Reuse existing utilities where appropriate.
- Add type hints to public interfaces when practical.
- Validate external input when possible.
- Log unexpected failures with useful context.
- Catch specific exceptions instead of broad exceptions.
- Do not silently ignore exceptions.
- Do not use `print()` for diagnostics.
- Keep functions and classes focused on a single responsibility.

Avoid:

- Duplicate abstractions
- Hidden behavior
- Provider-specific branching in shared code
- Hardcoded configuration values
- Embedded secrets or credentials

## Configuration

Configuration should be provided through documented configuration files or environment variables.

When introducing a configuration option:

1. Add it to `.env.sample`.
2. Document its purpose and default value.
3. Provide a safe default whenever possible.

Do not hardcode:

- API keys
- User IDs
- Guild IDs
- Provider URLs
- Machine-specific paths

## Compatibility

Maintain compatibility whenever practical.

When compatibility must change:

- Document the change.
- Update affected documentation.
- Update affected tests.

Do not modify tests simply to hide implementation issues.

## Documentation

Documentation is part of the implementation.

Update documentation whenever behavior or architecture changes.

Documentation should follow:

- `docs/writing-style.md`
- ASD-STE100 Simplified Technical English for all project documentation
- The project’s Markdown linting rules

This includes:

- README files
- Architecture documents
- ADRs
- Reports
- Examples
- User-facing comments

Treat documentation quality as part of code quality.

## Pull requests

Keep pull requests focused.

Include only changes related to the same objective.

For architectural changes:

- Explain the reasoning.
- Describe compatibility implications.
- Update relevant documentation.
- Update tests when appropriate.

Large architectural changes should be discussed before implementation.

## Final principle

When uncertain, follow the existing architecture.

Favor:

- Explicit interfaces
- Provider independence
- Composition
- Clear ownership
- Predictable behavior
- Long-term maintainability
