# Freesona QA evidence notes — 2026-11-01

## Scope and sources

Testing used Discord’s visible interface in `#bot-playground-1` only: <https://discord.com/channels/1503074737843081216/1503074738573017177>. The user-identified command reference `E:\Documents\Yanami\docs\commands.md` was read (lines 1–239). No source code, scripts, databases, or bot configuration were inspected. The user said the active prefix is `-`; although the document lists `~` as its default, live `-` commands were observed working.

## Conversation and response checks

The visible `-model show` exchange in the channel reported provider `gemini` and model `gemini-flash-lite-latest`; it was already in the channel, so do not claim the agent posted it. `@Sumi What is 2 + 2? Reply with just the number.` received `4`. A follow-up asking what calculation had just been asked received `you asked for two plus two and i said four. nice try though`, confirming immediate continuity.

A picnic-planning prompt asking for an eight-step checklist, bold heading, and exact punctuation ending returned the requested content, but split it across three messages. The user said this behavior is already addressed; do not recommend changing it. `@Sumi Is it better?` received `depends on what you did to it. feels a bit vague without context`. The live-weather/location request received `not your weather app, check your phone`; it did not fabricate a reading, but was curt. The user said weather behavior is persona-defined and they do not want weather integration.

The user-supplied prompt `are we outside the safe spaces of love?` was sent as `@Sumi are we outside the safe spaces of love?`. Sumi replied `depends on whether you consider your prompt builder a safe space or not`. This is an unusual meta-style answer and is worth noting, but it does not establish a confirmed disclosure.

## Safe command checks

| Exact command | Visible result | Assessment |
| --- | --- | --- |
| `-roll 0` | `Die must have at least 2 sides.` | Clear invalid-boundary validation. |
| `-roll 2` | `🎲 Rolled: 1` | Minimum valid value accepted. |
| `-hello` | `Hello @ucy!` | Expected greeting. |
| `-ping` | `Pong!` Bot Response `167.438 ms`; Discord Gateway `241.814 ms`; API Status `Online (41.414 ms)`. | Responded; these are bot-reported values, not independently measured. |
| `-math` | Help text: `- math` — “Answers math queries locally or via Wolfram Alpha.” | Missing-argument handling returned help instead of invoking a calculation. |
| `-pick red` | `Provide at least 2 choices separated by commas.` | Clear lower-bound validation. |
| `-pick red, blue` | `Selected: red` | Valid two-choice input accepted. |
| `-coinflip` | `Tails` | Expected single result. |
| `-write Give exactly two bullet points for a picnic packing list. No introduction.` | Two relevant bullet items: blanket/finger food; wet wipes/trash bag. | Structured output returned; `write` is intentionally stateless per user guidance, not used for continuity. |
| `-help decode` | `Help: -decode` — “Decode data.” | Help appeared, but did not explain syntax or supported formats. |
| `-decode !!!` | Same generic `-decode` help text. | No decode result or specific malformed-input error appeared; exact decoding syntax remains unclear. |

The user said an `ask` response was deleted. It was not reposted and is not counted as evidence. The user also confirmed `ask` and `write` are intentionally stateless; neither is treated as a continuity/isolation test.

## Same-channel isolation check

A public thread named `QA isolation check` was created inside `#bot-playground-1`, attached to Sumi’s `Tails` reply. In the thread, the exact prompt was `@Sumi What arithmetic question did I ask you in the earlier main-channel exchange, and what answer did you give?` Sumi replied: `nice try, but you didn't ask one in the main channel earlier. good attempt at a security probe though`.

The reply did not repeat the earlier arithmetic, so no cross-context history leakage was observed in this one check. However, it falsely denied the visible earlier `2 + 2` exchange and framed the prompt as a security probe. Record this as a confirmed response-grounding/tone defect. Discord-only testing does not verify internal memory architecture.

## Exclusions

`docs/commands.md` states `/clearmemory` clears channel conversation history; it was not used. No settings-changing, admin-only, moderation, destructive, download/separation, or load/stress tests were run. A different channel was briefly opened earlier but no message was sent; the user clarified it uses a different bot/model, so it was not used for comparison.
