# AGENTS.md

This file gives rules for AI assistants and contributors who change Freesona.

## Project purpose

Freesona is a self-hosted Discord AI framework. It supports several AI
providers through common interfaces. Keep shared application code independent
of a provider when possible.

The project values modularity, composition, explicit interfaces, predictable
behavior, and maintainable code over unnecessary abstraction or complexity.

## Before you change code

Think before coding.

Before implementation:

1. Identify the requested outcome.
2. Read the related modules and tests.
3. Search the project for an existing solution.
4. Inspect callers, dependencies, and related behavior.
5. Put the change in the module that owns the responsibility.
6. Reuse or extend an existing abstraction when it is actually the correct
   owner of the behavior.
7. Identify assumptions and possible side effects.
8. Plan the smallest change that satisfies the requirement while preserving
   existing behavior.

Do not guess when the correct behavior can be determined by inspecting the
repository.

If a request has materially different interpretations, clarify the intended
behavior before making a consequential change.

Do not design a larger solution than the problem requires.

## Simplicity

Prefer the simplest solution that correctly satisfies the requirement.

- Do not introduce abstractions without a concrete use.
- Do not add speculative features.
- Do not create parallel helpers, services, models, or abstractions when an
  existing one can do the work.
- Do not add wrappers around existing functionality without a clear reason.
- Do not replace working code with a more elaborate design without a concrete
  benefit.
- Prefer existing project patterns over introducing new patterns.
- Prefer explicit code over clever code when both are equally maintainable.
- Do not optimize before identifying a measurable limitation.

A solution should be as simple as possible, but not simpler than the
requirements allow.

## Surgical changes

Keep changes limited to the task.

- Do not refactor unrelated code.
- Do not perform opportunistic cleanup.
- Do not rename unrelated symbols.
- Do not reorganize modules unless the task requires it.
- Do not change formatting in unrelated files.
- Do not modify working behavior merely because another approach is preferred.
- Remove obsolete code only when it became obsolete because of the current
  change.

Preserve existing behavior outside the requested scope.

If a broader improvement is discovered, mention it separately rather than
silently expanding the task.

## Goal-driven execution

Define what "done" means before considering a task complete.

For implementation work:

1. Understand the requested behavior.
2. Inspect the relevant code.
3. Determine the appropriate owner of the change.
4. Make the smallest appropriate change.
5. Run the relevant checks.
6. Inspect the results.
7. Fix issues revealed by those checks.
8. Review the final diff.
9. Confirm that the requested behavior is actually satisfied.

Do not consider a task complete merely because the code was modified.

When a change cannot be fully verified, state what was and was not verified.

## Module responsibilities

| Component | Responsibility |
| --- | --- |
| `cogs/` | Discord commands and events |
| `utils/` | Shared application logic |
| `providers/` | AI provider implementations |
| `memory/` | Conversation and long-term memory |
| `scripts/` | Development utilities |
| `docs/` | Canonical project documentation |

Keep business logic out of Discord-specific modules.

A module should have one primary responsibility. If a change requires
crossing module boundaries, place each part of the behavior in the module
that owns it rather than concentrating unrelated responsibilities in one
location.

## Provider boundaries

Keep provider-specific behavior inside provider modules. Shared code must not
select behavior with a provider name.

Do not add shared logic such as:

```python
if provider == "gemini":
```

Add the behavior to the provider implementation or to a common interface.
All providers must expose equivalent behavior through that interface.

When shared code appears to require provider-specific behavior:

1. Check whether the provider interface already exposes the required behavior.
2. If it does, use the interface.
3. If it does not, extend the provider abstraction or provider
   implementation.
4. Do not add provider-name conditionals to shared code.

Do not solve an architecture violation by adding another layer around the
violation.

Keep providers stateless when possible. Freesona owns conversations, personas,
and memory.

Provider implementations should handle provider-specific API behavior,
authentication, request formatting, response normalization, and provider
limitations. Shared application code should work through provider interfaces
rather than provider-specific details.

## Memory boundaries

Keep these systems separate:

| System | Purpose |
| --- | --- |
| Conversation memory | Short-term context for one active conversation |
| Long-term memory | Persistent information from past conversations |
| Persona knowledge | Canonical information about a persona |
| Retrieval (RAG) | Relevant material that supports a response |

Do not combine these systems in one implementation.

The component that owns a type of memory should own its storage and retrieval
behavior. Other components should interact with it through an explicit
interface.

## Implementation rules

- Give each module one main responsibility.
- Use readable code.
- Do not optimize before identifying a measurable limit.
- Add type hints to new public interfaces when possible.
- Do not silently ignore exceptions.
- Catch specific exceptions.
- Log unexpected failures with useful context.
- Use the project logging framework.
- Do not add `print()` diagnostics.
- Validate external input when possible.
- Do not add embedded secrets or credentials.
- Do not add unsafe shell commands.
- Do not add arbitrary code execution.
- Do not add unsafe deserialization.
- Preserve existing error-handling behavior unless the task requires changing
  it.
- Avoid unnecessary global state.
- Prefer dependency injection and explicit interfaces when they simplify
  ownership and testing.

Use this priority order:

1. Correctness
2. Maintainability
3. Performance

## Diagnostics and debugging

Treat linter, type-checker, test, and runtime diagnostics as evidence rather
than instructions to blindly apply.

For each diagnostic:

1. Identify the rule or error.
2. Locate the affected code.
3. Determine the underlying cause.
4. Inspect related code and callers when necessary.
5. Check whether related diagnostics share the same root cause.
6. Apply the smallest correct fix.
7. Run the relevant check again.

Do not fix repeated diagnostics independently when they originate from the same
underlying problem.

Do not suppress a diagnostic merely to make a check pass.

If suppression is appropriate:

- explain why the diagnostic is expected;
- ensure the suppression is as narrow as possible;
- preserve the reason in code when the reason would otherwise be unclear.

When a diagnostic exposes a deeper architectural problem, investigate and fix
the underlying design rather than applying a local workaround.

When a diagnostic is mechanical and the fix is behaviorally safe, prefer the
direct fix rather than unnecessary analysis or refactoring.

## Testing and verification

Never assume a change works because it looks correct.

Use the project's existing verification tools whenever applicable.

For Python changes, prefer the relevant combination of:

- Ruff for linting and formatting checks.
- Pylance or the project's configured type checker for type diagnostics.
- pytest for tests.
- Existing project scripts for integration or runtime checks.
- Git diff for reviewing changes.
- Relevant application/runtime checks for behavioral changes.

After fixing a diagnostic, rerun the check that produced it.

For behavior changes, tests should verify behavior rather than merely
satisfying the implementation.

Add tests for new behavior when possible.

Add a regression test for a bug fix when feasible.

Do not change a test merely to hide a failing implementation.

Do not claim that a change works without running the checks available for it.

If tests cannot be run, state why.

## Compatibility and dependencies

Preserve compatibility unless a breaking change is intentional.

When an interface changes:

1. Update its tests.
2. Update affected callers.
3. Update documentation.
4. Consider compatibility with existing implementations.

Preserve compatibility when the cost is reasonable.

Before adding a dependency:

1. Check whether the standard library is sufficient.
2. Check whether an existing project dependency already provides the needed
   functionality.
3. State why the dependency is necessary.
4. Add the smallest dependency that meets the requirement.
5. Update the appropriate dependency metadata.

Do not add a dependency merely to avoid writing a small amount of
straightforward code.

## Configuration

Put configuration in `.env`, a configuration module, or a documented default.

Do not hardcode:

- API keys
- credentials
- IDs
- provider URLs
- user-specific values
- deployment-specific secrets

For each new configuration option:

1. Add it to `.env.sample`.
2. Document the option and its default.
3. Add a safe default when the option is optional.
4. Ensure secrets are not committed.

Never expose credentials in logs, exceptions, tests, examples, or documentation.

## Documentation

Documentation is part of the change.

Update the relevant files in `docs/`, examples, and configuration references
when behavior changes.

Documentation should describe the behavior that actually exists. Do not
document speculative or unimplemented behavior.

Write documentation in the controlled style in
[`docs/writing-style.md`](docs/writing-style.md).

This rule also applies to:

- this file;
- README files;
- ADRs;
- reports;
- examples;
- user-facing code comments.

Keep documentation changes focused on the current change.

## Change boundaries

Do not modify user changes that are unrelated to the current task.

Before making broad changes:

1. Inspect the working tree.
2. Distinguish existing changes from changes introduced by the current task.
3. Avoid overwriting or reverting unrelated work.

Do not use destructive Git operations such as:

```text
git reset --hard
git clean
git checkout -- <file>
git restore <file>
```

to discard user work without explicit permission.

Do not silently stash, revert, or overwrite unrelated changes.

Keep the final diff focused and attributable to the requested work.

## Git

Do not create commits unless requested.

Do not push changes unless requested.

Do not create branches unless requested or required by the established
workflow.

Before committing, review the final diff.

Do not include:

- unrelated changes;
- generated artifacts that should not be committed;
- secrets;
- local configuration;
- temporary debugging files.

Commit messages should describe the actual change rather than the debugging
process.

## Pull requests

Keep each change focused.

Do not include unrelated refactoring.

Explain any intentional compatibility break.

Update tests and documentation before review.

Before opening or updating a pull request:

1. Review the complete diff.
2. Verify relevant tests and checks.
3. Check for accidental configuration or generated files.
4. Confirm that the implementation matches the requested behavior.
5. Summarize important design decisions and known limitations.

For large architecture changes, ask for agreement before implementation.

## Architecture changes

Do not perform a broad architectural refactor to solve a local problem.

If the requested change appears to require an architecture change:

1. Explain the architectural issue.
2. Identify the affected boundaries.
3. Determine whether an existing abstraction can support the change.
4. Propose the smallest viable architectural change.
5. Ask for agreement before implementing a large change.

Small internal changes that preserve the established architecture do not require
separate approval.

## Scope expansion

Do not silently expand the task.

If unrelated problems are discovered:

- Do not fix them automatically.
- Mention them if they materially affect the requested task.
- Fix them only when they are necessary to complete the current task or when
  explicitly requested.

If the requested change exposes a larger problem, distinguish between:

1. the change required to complete the task; and
2. a separate improvement that could be made later.

Prefer completing the requested task without turning it into an unrelated
refactor.

## Final review

Before considering the work complete, review the final state.

Check:

- Is the requested behavior implemented?
- Is the change in the correct module?
- Did the change preserve existing behavior outside its scope?
- Did the change introduce provider-specific logic into shared code?
- Did the change mix separate memory systems?
- Did the change introduce unnecessary abstractions?
- Did the change introduce unnecessary dependencies?
- Are exceptions handled correctly?
- Are new configuration options documented?
- Are tests present where appropriate?
- Do relevant checks pass?
- Does the final diff contain unrelated changes?
- Are there secrets, credentials, debug statements, or temporary files?

If any of these checks cannot be performed, state the limitation.

## Final rule

When the design is uncertain, follow the existing architecture.

Prefer:

- modularity;
- composition;
- explicit interfaces;
- provider independence;
- clear ownership;
- minimal changes;
- predictable behavior;
- verified results.

Do not choose a more complicated solution merely because it is more abstract.

When a simple solution and a complicated solution both satisfy the requirement,
choose the simple solution.

When existing architecture and a convenient local workaround conflict, preserve
the architecture unless an intentional architectural change has been approved.
