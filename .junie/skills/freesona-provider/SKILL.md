---
name: freesona-provider
description: Rules for modifying Freesona's LLM provider abstraction layer.
---
# Freesona LLM Providers

This skill governs your changes to how Freesona interacts with LLM APIs. Inspect your `dev` branch architecture before you modify provider code.

## Your Inspection Requirements
Before you make changes, determine:
- Your base provider interfaces and implementations.
- The exact boundaries of your generation calls.
- Configuration and provider-specific options.
- Error handling and fallback behavior.
- How your providers receive constructed prompts.
- Statelessness assumptions.
- Relevant tests.

## Strict Boundaries
- **Prompt Construction:** Providers execute prompts; they do not assemble them. Keep your prompt-building logic out of this layer.
- **State:** Do not store conversation or persistent memory state in provider implementations unless the existing architecture explicitly requires it.

## Modification Rules
- Maintain your provider independence.
- Do not hardcode provider-specific logic into your core systems unless a pattern already exists.
- Verify your provider behavior against existing tests. Do not assume a provider is active just because configuration keys exist.
