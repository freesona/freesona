---
name: discord-py
description: Reference for discord.py library behavior.
---
# discord.py Rules

This skill governs your use of the `discord.py` library. Rely only on the official documentation.

## Cogs and Extensions
- Your Cogs must be classes that inherit from `commands.Cog`.
- Register your Cogs asynchronously using `await bot.add_cog(MyCog(bot))`.
- Remove Cogs asynchronously using `await bot.remove_cog('CogName')`.
- Your extension entry points require an async `setup` function: `async def setup(bot):`.

## Commands and Listeners
- Mark your Cog commands with the `@commands.command()` decorator.
- Every command inside a Cog must take a `self` parameter before `ctx` or `interaction`.
- Mark listeners inside your Cogs with `@commands.Cog.listener()`.
- Use `@commands.hybrid_command()` for commands that support both text and slash execution.

## Interactions
- Use `discord.Interaction` for application-command and component interactions.
- An interaction can have one initial response.
- Use `await interaction.response.send_message()` for the initial response.
- Use `await interaction.response.defer()` when you need to acknowledge the interaction before completing the work.
- After the initial response or defer, use `await interaction.followup.send()` for additional messages.
- Follow the official interaction lifecycle rather than attempting multiple initial responses.

## Background Tasks
- Use `discord.ext.tasks` when the task matches the extension's periodic-loop model.
- Use `@tasks.loop(...)` for recurring task loops.
- Start and stop loops according to the lifecycle of the owning component.
- Cancel or otherwise clean up loops when the owning component is unloaded.
