---
name: freesona-prompting
description: Rules for modifying Freesona's prompt and context assembly.
---
# Freesona Prompt Assembly

This skill governs your changes to how Freesona builds LLM prompts. Inspect your actual pipeline on the `dev` branch before you modify it.

## Your Inspection Requirements
Before you change the prompt builder, determine:
- Where you assemble system instructions.
- How you load persona definitions.
- How you append conversation history.
- How you inject long-term memory and PKB results.
- The order and prioritization of your context blocks.
- Token-budget enforcement rules.
- Your provider-facing prompt format.
- Relevant tests.

## Strict Boundaries
- **Memory/PKB Retrieval:** Your prompt builder consumes retrieved facts. Do not move your actual database retrieval logic into the prompt builder.
- **Provider Layer:** The prompt builder formats context. It does not execute your LLM request.

## Modification Rules
- Apply context only where your current architecture specifies.
- Do not move memory, persona, or provider logic into the prompt builder unless the existing architecture already does.
- Do not restructure unrelated systems under the guise of prompt tuning.
