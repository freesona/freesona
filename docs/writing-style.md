# Documentation writing style

Use this style for all project documentation. All repository documentation must
adhere to ASD-STE100 Simplified Technical English. This guide applies the
practical rules of ASD-STE100 to Freesona documentation.

## Purpose

Write text that a reader can understand on the first read. State what the
system does, why it does it, and what the reader must do.

Use the official ASD-STE100 specification when a controlled-dictionary decision
is required. This guide does not replace that specification.

## Write clear sentences

- Use short sentences. Prefer 20 words or fewer. Split a sentence that has
  more than one condition or action.
- Use active voice. Name the component that performs the action.
- Use the present tense for normal behavior.
- Put the main action near the start of an instruction.
- Give one instruction for each action.
- Use a noun consistently. Do not use a synonym for the same component.
- Use articles (`a`, `an`, and `the`) when they help identify an item.
- Avoid vague words such as `it`, `this`, `thing`, `easy`, `quick`, and
  `appropriate` when a specific noun or condition is available.

Write `The ConversationManager stores recent messages.` Do not write
`Recent messages are stored.`

## Use controlled words

Prefer common technical words with one meaning. Use these forms in new text:

| Prefer | Avoid |
|---|---|
| `use` | `utilize`, `leverage` |
| `start` | `launch`, `initiate` |
| `stop` | `terminate` |
| `select` | `choose` |
| `make sure` | `ensure` |
| `show` | `display`, `surface` |
| `change` | `modify`, `alter` |
| `get` | `retrieve`, when the technical meaning is not important |
| `must` | `should`, for a mandatory requirement |

Keep established technical names unchanged. Examples include `PromptBuilder`,
`ChromaDB`, `RAG`, `Discord`, command names, file paths, API names, and code
identifiers.

## Write instructions

Start each instruction with an imperative verb. State the condition before the
action when the action depends on it. State the expected result after the
action when it helps the reader verify success.

```text
1. Copy `.env.sample` to `.env`.
2. Set the API key for the selected provider.
3. Run `python scripts/check_project.py`.
```

Do not combine unrelated actions in one list item. Do not use a negative
instruction when a direct positive instruction is possible.

## Describe behavior and limits

State the owner of each action, state change, and limit. Use `must` for a
mandatory invariant. Use `can` only for an available capability. State the
scope of stored data, including guild, channel, user, and persona boundaries.

```text
The Character Memory store must use the guild, user, and persona identifiers.
It must not use the channel identifier as part of the storage key.
```

## Format Markdown

- Use one H1 heading in each document.
- Use descriptive headings that start with a noun or verb.
- Put a blank line before and after lists, tables, and code blocks.
- Give each table a header row and a separator row.
- Use `mermaid` after the opening fence for flowcharts, sequence diagrams, class diagrams, and state diagrams.
- Use `text` after the opening fence for simple ASCII art or fixed-width layouts that do not render well as Mermaid.
- Use complete sentences in prose. Tables may use sentence fragments when the column header supplies the missing context.
- Keep code, identifiers, commands, paths, and exact user-interface text in backticks.

## Review checklist

Before you publish a documentation change, check the following items:

- Each sentence has one clear main action or fact.
- Each required action has an actor and a condition.
- Terms have one meaning throughout the document.
- The text does not use marketing language or unsupported claims.
- Examples match the current code and configuration.
- Tables and fenced blocks render correctly.
