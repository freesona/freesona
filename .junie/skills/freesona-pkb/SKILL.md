---
name: freesona-pkb
description: Rules for modifying Freesona's Persona Knowledge Base (PKB).
---
# Freesona PKB

This skill governs your changes to the ChromaDB-backed Persona Knowledge Base. Verify your actual implementation on the `dev` branch before you modify it.

## Your Inspection Requirements
Before you alter the PKB, inspect the repository to locate:
- Your ChromaDB collection structures and modules.
- The metadata schema.
- Your data ingestion pipeline and source material.
- Embedding configurations.
- Persona association rules.
- Retrieval and filtering logic.
- The integration point with your RAG pipeline.
- Relevant tests.

## Strict Boundaries
- **User Memory:** Keep persistent user facts separate from persona knowledge.
- **Conversation State:** Do not store transient context in your PKB.
- **Persona Definition:** The PKB stores knowledge, not your persona's base identity or behavior instructions.

## Modification Rules
- Maintain the exact schema and filtering rules found in your current implementation.
- Read your existing tests to understand update and deletion constraints before you change them.
