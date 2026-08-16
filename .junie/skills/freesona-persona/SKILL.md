---
name: freesona-persona
description: Rules for modifying Freesona's persona and identity system.
---
# Freesona Persona

This skill governs your changes to Freesona's identity and behavior instructions. Inspect your `dev` branch implementation before you modify personas.

## Your Inspection Requirements
Before you change persona code, determine:
- How you format and store persona definitions.
- Where your identity and behavior instructions live.
- How your persona config reaches the prompt generation pipeline.
- The established relationship between your persona definition and the PKB.
- Persona-specific state (if any exists).
- Relevant tests.

## Strict Boundaries
- **PKB:** Your persona definition is the core identity. The PKB is supplementary knowledge. Do not treat them as the same component.
- **User Memory:** Do not store factual user memory inside your persona configuration.
- **Conversation State:** Separate your static persona traits from transient chat data.

## Modification Rules
- Respect the existing structure for your persona traits and instructions.
- Do not add state to personas unless your current implementation supports it.
