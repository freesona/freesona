# cogs/ai/genai_generation.py: AI generation commands (~write, ~ask, etc.).

import urllib.parse

import discord
from discord.ext import commands

from utils.config import embed_footer
from utils.generation import (
    ConversationResponse,
    extract_attachments,
    safe_generate,
)
from utils.persona import CURRENT_PERSONA, CURRENT_PERSONA_ID

from .genai_common import BOT_NAME, clean_sources_block, logger


class GenAIGenerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------------
    # ~write
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="write",
        aliases=["w"],
        help="Ask the AI to write or create something.",
    )
    async def write_cmd(self, ctx: commands.Context, *, query: str):
        guild = ctx.guild
        if guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return

        attachments = (
            await extract_attachments(ctx.message) if ctx.message else []
        )
        response: ConversationResponse | None = None

        if ctx.interaction:
            await ctx.defer()
            response = await safe_generate(
                query,
                current_persona=CURRENT_PERSONA,
                persona_id=CURRENT_PERSONA_ID,
                instruction_prefix=(
                    "Return plain text only. "
                    "Use double newlines between paragraphs. "
                    "Do NOT use markdown, symbols, or headings. "
                    "Each idea must be separated clearly."
                ),
                apply_persona=True,
                guild_id=guild.id,
                user_id=ctx.author.id,
                message_id=ctx.message.id if ctx.message else None,
                channel_id=ctx.channel.id,
                username=ctx.author.display_name,
                attachments=attachments,
            )
        else:
            async with ctx.typing():
                response = await safe_generate(
                    query,
                    current_persona=CURRENT_PERSONA,
                    persona_id=CURRENT_PERSONA_ID,
                    instruction_prefix=(
                        "Return plain text only. "
                        "Use double newlines between paragraphs. "
                        "Do NOT use markdown, symbols, or headings. "
                        "Each idea must be separated clearly."
                    ),
                    apply_persona=True,
                    guild_id=guild.id,
                    user_id=ctx.author.id,
                    message_id=ctx.message.id if ctx.message else None,
                    channel_id=ctx.channel.id,
                    username=ctx.author.display_name,
                    attachments=attachments,
                )

        if response is None:
            logger.error(
                "Write command completed without a generation response."
            )
            await ctx.send("The response could not be generated.")
            return

        embed = discord.Embed(
            title=f"{BOT_NAME} says...",
            description=response.first_text(),
            color=discord.Color.green(),
        )
        embed.set_footer(text=embed_footer(ctx.author.display_name, query))
        await ctx.send(embed=embed)

    # -------------------------------------------------------------------
    # ~ask
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="ask", aliases=["a"], help="Ask the AI a question."
    )
    async def ask_cmd(self, ctx: commands.Context, *, query: str):
        guild = ctx.guild
        if guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return

        attachments = (
            await extract_attachments(ctx.message) if ctx.message else []
        )
        response: ConversationResponse | None = None

        if ctx.interaction:
            await ctx.defer()
            response = await safe_generate(
                query,
                current_persona=CURRENT_PERSONA,
                persona_id=CURRENT_PERSONA_ID,
                instruction_prefix=(
                    "Write in clean paragraphs. "
                    "Use newline breaks between sections. "
                    "Do NOT use markdown headings like ###."
                ),
                guild_id=guild.id,
                user_id=ctx.author.id,
                message_id=ctx.message.id if ctx.message else None,
                channel_id=ctx.channel.id,
                username=ctx.author.display_name,
                attachments=attachments,
            )
        else:
            async with ctx.typing():
                response = await safe_generate(
                    query,
                    current_persona=CURRENT_PERSONA,
                    persona_id=CURRENT_PERSONA_ID,
                    instruction_prefix=(
                        "Write in clean paragraphs. "
                        "Use newline breaks between sections. "
                        "Do NOT use markdown headings like ###."
                    ),
                    guild_id=guild.id,
                    user_id=ctx.author.id,
                    message_id=ctx.message.id if ctx.message else None,
                    channel_id=ctx.channel.id,
                    username=ctx.author.display_name,
                    attachments=attachments,
                )

        if response is None:
            logger.error(
                "Ask command completed without a generation response."
            )
            await ctx.send("The response could not be generated.")
            return

        embed = discord.Embed(
            title=f"{BOT_NAME} answers...",
            description=response.first_text(),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=embed_footer(ctx.author.display_name, query))
        await ctx.send(embed=embed)

    # -------------------------------------------------------------------
    # ~search
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="search",
        aliases=["s"],
        help="Search the web and summarize with AI.",
    )
    async def search_cmd(self, ctx: commands.Context, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return

        from utils.search import web_search

        result = None
        if ctx.interaction:
            await ctx.defer()
            result = await web_search(query)
        else:
            async with ctx.typing():
                result = await web_search(query)

        if result.failed:
            embed = discord.Embed(
                title=f"Search: {query}",
                description=(
                    "Search is temporarily unavailable (the search models are "
                    "overloaded or unreachable right now). Try again in a bit."
                ),
                color=discord.Color.red(),
            )
            url = f"https://www.google.com/search?q={
                urllib.parse.quote(query)}"
            embed.add_field(name="Full results", value=url, inline=False)
            embed.set_footer(text=embed_footer(ctx.author.display_name, query))
            await ctx.send(embed=embed)
            return

        if result.has_sources:
            text = result.text[:4096]
        else:
            response: ConversationResponse | None = None
            if ctx.interaction:
                response = await safe_generate(
                    f"Summarize these search results:\n\n{result.text}",
                    current_persona=CURRENT_PERSONA,
                    persona_id=CURRENT_PERSONA_ID,
                    apply_persona=False,
                    instruction_prefix=(
                        "Write in natural, flowing paragraphs. "
                        "Do not use bullet points or one-sentence sections. "
                        "Use **Bold Text** only for key terms. "
                        "Do not use markdown headers (#)."
                    ),
                )
            else:
                async with ctx.typing():
                    response = await safe_generate(
                        f"Summarize these search results:\n\n{result.text}",
                        current_persona=CURRENT_PERSONA,
                        persona_id=CURRENT_PERSONA_ID,
                        apply_persona=False,
                        instruction_prefix=(
                            "Write in natural, flowing paragraphs. "
                            "Do not use bullet points or one-sentence "
                            "sections. "
                            "Use **Bold Text** only for key terms. "
                            "Do not use markdown headers (#)."
                        ),
                    )
            if response is None:
                logger.error(
                    "Search command completed without a generation response."
                )
                text = "Search results could not be summarized."
            else:
                text = response.first_text()[:4096]

        embed = discord.Embed(
            title=f"Search: {query}",
            description=text or "No results found.",
            color=discord.Color.blue(),
        )

        if result.has_sources:
            sources_text = clean_sources_block(
                result.sources_block(max_items=5)
            )
            embed.add_field(name="Sources", value=sources_text, inline=False)
        else:
            url = f"https://www.google.com/search?q={
                urllib.parse.quote(query)}"
            embed.add_field(name="Full results", value=url, inline=False)

        embed.set_footer(text=embed_footer(ctx.author.display_name, query))
        await ctx.send(embed=embed)
