# AGENTS.md

This file gives rules for AI assistants and contributors who change Freesona.

## Project purpose

Freesona is a self-hosted Discord AI framework. It supports several AI
providers through common interfaces. Keep shared application code independent
of a provider when possible.

## Before you change code

1. Read the related modules and tests.
2. Search the project for an existing solution.
3. Put the change in the module that owns the responsibility.
4. Reuse or extend an existing abstraction.
5. Plan a minimal change that keeps existing behavior.

Do not add a parallel helper, service, model, or abstraction when an existing
one can do the work.

## Module responsibilities

| Component | Responsibility |
|---|---|
| `cogs/` | Discord commands and events |
| `utils/` | Shared application logic |
| `providers/` | AI provider implementations |
| `memory/` | Conversation and long-term memory |
| `scripts/` | Development utilities |
| `docs/` | Canonical project documentation |

Keep business logic out of Discord-specific modules.

## Provider boundaries

Keep provider-specific behavior inside provider modules. Shared code must not
select behavior with a provider name.

Do not add shared logic such as:

```python
if provider == "gemini":
```

Add the behavior to the provider implementation or to a common interface.
All providers must expose equivalent behavior through that interface.

Keep providers stateless when possible. Freesona owns conversations, personas,
and memory.

## Memory boundaries

Keep these systems separate:

| System | Purpose |
|---|---|
| Conversation memory | Short-term context for one active conversation |
| Long-term memory | Persistent information from past conversations |
| Persona knowledge | Canonical information about a persona |
| Retrieval (RAG) | Relevant material that supports a response |

Do not combine these systems in one implementation.

## Implementation rules

- Give each module one main responsibility.
- Use readable code. Do not optimize before you identify a measurable limit.
- Add type hints to new public interfaces when possible.
- Do not silently ignore exceptions.
- Catch specific exceptions and log unexpected failures with useful context.
- Use the project logging framework. Do not add `print()` diagnostics.
- Validate external input when possible.
- Do not add embedded secrets, credentials, unsafe shell commands, arbitrary
  code execution, or unsafe deserialization.

Use this priority order: correctness, maintainability, then performance.

## Compatibility and dependencies

Preserve compatibility unless a breaking change is intentional. When an
interface changes, update its tests and documentation. Preserve compatibility
when the cost is reasonable.

Before you add a dependency:

1. Check whether the standard library is sufficient.
2. State why the dependency is necessary.
3. Add the smallest dependency that meets the requirement.

## Configuration

Put configuration in `.env`, a configuration module, or a documented default.
Do not hardcode API keys, IDs, provider URLs, or user-specific values.

For each new configuration option:

1. Add it to `.env.sample`.
2. Document the option and its default.
3. Add a safe default when the option is optional.

## Tests and documentation

Add tests for new behavior when possible. Add a regression test for a bug fix
when feasible. Do not change a test only to hide a failing implementation.

Documentation is part of the change. Update the relevant files in `docs/`,
examples, and configuration references when behavior changes.

Write documentation in the controlled style in
[`docs/writing-style.md`](docs/writing-style.md). This rule also applies to
this file, README files, ADRs, reports, examples, and code comments that users
read.

## Pull requests

Keep each change focused. Do not include unrelated refactoring. Explain any
intentional compatibility break. Update tests and documentation before review.

For large architecture changes, ask for agreement before implementation.

## Final rule

When the design is uncertain, follow the existing architecture. Prefer
modularity, composition, explicit interfaces, provider independence, and
predictable behavior.
