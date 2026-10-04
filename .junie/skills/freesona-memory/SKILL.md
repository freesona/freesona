---
name: freesona-memory
description: Instructions for an autonomous coding agent to safely understand, modify, test, and extend Freesona's memory-related systems.
---

# Freesona Memory Architecture

This Agent Skill guides you in working with Freesona's memory architecture. Freesona separates short-term conversation state, long-term persistent user facts, and persona knowledge (PKB).

## Pre-Modification Code Inspection

Before making changes, inspect the current `dev` branch and locate the exact implementations. Do not assume standard names or file paths.

Locate and verify:

* The memory modules.
* The conversation-state implementation.
* The SQLite database implementation.
* The ChromaDB/PKB implementation.
* The memory extraction pipeline.
* The retrieval/RAG orchestration components.
* Existing `AGENTS.md` rules.
* Relevant architecture documentation in `docs/`.
* Tests covering the affected behavior.

Follow the repository's `AGENTS.md` instructions. This skill supplements project-level rules with memory-specific guidance and must not contradict them.

## Architectural Domains

Identify the responsible module for each domain before modifying code.

* **Conversation Memory:** Manages short-term context for an active conversation.
* **Long-Term User Memory:** Persistent user facts extracted from conversations and stored according to the project's existing memory pipeline. Inspect the actual extraction and storage components before modifying them.
* **Persona Knowledge (PKB):** A distinct system utilizing ChromaDB. ChromaDB is independent of user facts unless the code explicitly establishes a relationship. Do not assume SQLite user facts have corresponding ChromaDB vectors.
* **Retrieval (RAG):** Retrieves relevant information for the current interaction. Identify the actual orchestration component rather than assuming a particular filename or module.
* **Persona and Generation:** These components may consume memory-related context but do not own memory storage, extraction, or retrieval logic.

## Memory Lifecycle: Extraction vs. Retrieval

Explicitly distinguish between these operations:

* **Memory Extraction:** Determines whether information from an interaction should become persistent memory. Inspect the actual implementation for importance thresholds, validation rules, extraction behavior, and write conditions. Do not persist every user message.
* **Memory Retrieval:** Determines which existing information is relevant to the current interaction. Retrieval relevance does not by itself establish that a retrieved fact is true, current, or identical to another fact.

Do not conflate extraction with retrieval.

## Persistent Memory and Fact Identity

* **Semantic Similarity vs. Factual Identity:** Semantic similarity does not prove factual identity. For example, "User lives in New York" and "User lives in Tokyo" are semantically related but contradictory.
* **Conflict Resolution:** Inspect the codebase before modifying how facts are stored or updated. Look for existing duplicate handling, stale-memory replacement, timestamps, confidence scores, and contradiction handling. Do not invent a conflict-resolution system if the repository lacks one. Treat unsupported mechanisms as potential future improvements rather than existing behavior.
* **Provenance:** Inspect the stored metadata. Preserve and use provenance data if the system tracks message IDs, channels, timestamps, or other source information. Do not invent new provenance fields.
* **Retention:** Inspect the existing retention and cleanup behavior before changing memory lifecycle rules. Do not assume long-term memory means permanent retention.

## Deletion

Check the actual deletion commands, functions, and storage behavior when implementing or modifying deletion flows.

* Determine the current scope of deletion. It may target a user, guild, conversation, individual fact, or another defined scope.
* Do not assume deleting a long-term user fact also deletes conversation history or PKB content.
* Verify whether the affected data crosses storage-system boundaries before performing cross-system deletions. Do not perform ChromaDB operations merely because a SQLite memory operation is being changed.
* Do not assume every record in one storage system has a corresponding record in another.

## Scope and Architecture

Preserve the existing architecture during ordinary tasks.

If a user explicitly requests an architectural migration, evaluate the requested change against the existing architecture and requirements rather than treating the current implementation as permanently immutable.

For normal tasks:

* Avoid unnecessary refactoring.
* Reuse existing abstractions.
* Modify the module that owns the affected responsibility.
* Do not create parallel implementations for functionality that already exists.
* Maintain LLM provider independence.
* Preserve existing boundaries between conversation state, long-term memory, PKB, retrieval, persona, and generation.

## Testing Expectations

Use the project's existing testing conventions.

* Test the specific storage layer that was changed.
* Test extraction behavior when extraction logic changes.
* Test retrieval behavior when retrieval logic changes.
* Test integration boundaries when changes span multiple memory components.
* When applicable, add regression tests for empty-memory cases, invalid memory extraction, duplicate or conflicting facts, and deletion flows.
* Do not require tests for unrelated memory systems. For example, a SQLite-only change does not automatically require ChromaDB tests.

## Adjacent Concerns

If a task crosses into another responsibility, follow the responsible module and its project documentation rather than duplicating that logic in the memory system.

* **Discord Events/Commands:** Follow the relevant Discord components.
* **LLM Providers:** Follow the relevant provider/generation components.
* **Persona/Prompt Definition:** Follow the relevant persona and prompt components.
