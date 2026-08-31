# Provider Independence

This document follows ASD-STE100 Simplified Technical English.

> "Providers are implementation details, not architectural foundations."

## Purpose

This document explains why Freesona is designed to remain independent of any individual AI provider and why provider abstraction is considered one of the project's core architectural principles.

---

## Philosophy

Large language model providers change frequently.

Models are renamed.
APIs evolve.
Pricing changes.
Companies discontinue products.

Freesona should continue functioning regardless of those changes.

The architecture therefore treats providers as interchangeable implementations behind a stable interface.

---

## Why Provider Independence Exists

Provider independence exists to avoid vendor lock-in.

No single provider should dictate:

- project architecture
- command implementations
- memory systems ([05-character-memory.md](./05-character-memory.md))
- prompt construction ([04-promptbuilder.md](./04-promptbuilder.md))
- configuration layout

Changing providers should require configuration changes, not architectural rewrites.

---

## Common Interface

All providers should expose the same capabilities whenever practical.

```text
Discord Cog
      │
      ▼
Generation Pipeline
      │
      ▼
Provider Interface
      │
 ┌────┴───────────────┐
 │                    │
Gemini            OpenAI
Ollama            Groq
Azure             OpenRouter
NVIDIA NIM        Future Providers
```

Discord commands should not need to know which provider ultimately generates the response.

---

## Benefits

## Consistency

Every provider behaves similarly from the perspective of the rest of the application.

---

## Extensibility

Adding support for another provider should primarily involve implementing the provider interface rather than modifying existing commands.

---

## Testing

A common interface makes providers easier to compare and validate.

Tests can verify expected behaviour without depending on a single vendor.

---

## Longevity

Providers may disappear.

Architecture should survive those changes.

---

## What Should Not Depend on Providers

Provider-specific logic should not appear inside:

- Discord cogs
- Memory
- Configuration parsing
- Prompt construction
- Business logic

Those components should communicate only through shared abstractions.

---

## Optional Provider Features

Providers inevitably expose unique capabilities.

Whenever practical:

- common functionality belongs in the shared interface
- provider-specific extensions should remain isolated

Avoid allowing one provider's unique feature to reshape the architecture for every other provider.

---

## Future Providers

Adding a provider should generally involve:

1. Implementing the provider interface.
2. Registering the provider.
3. Adding configuration.
4. Testing compatibility.

Existing commands should require little or no modification.

---

## Long-term Vision

Provider independence is not merely about supporting many providers.

It protects Freesona from technological shifts and allows users to choose the provider that best fits their needs without sacrificing functionality.

---

## Related Research

- Architecture Philosophy ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- PromptBuilder ([04-promptbuilder.md](./04-promptbuilder.md))
- Character Memory ([05-character-memory.md](./05-character-memory.md))
- Identity Framework ([02-identity-framework.md](./02-identity-framework.md))
- Rejected Ideas ([10-rejected-ideas.md](./10-rejected-ideas.md))
