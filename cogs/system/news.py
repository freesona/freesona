#!/usr/bin/env python3
# cogs/system/news.py: RSS/Atom news feed commands and auto-posting loop.
import asyncio
import logging
from urllib.parse import urljoin, urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.config import load_config, save_config
from utils.rss import (
    delete_rss_feed,
    load_rss_feeds,
    load_seen_links,
    mark_links_seen,
    parse_feed,
    save_rss_feed,
)
from utils.security import is_public_http_url

logger = logging.getLogger("FreesonaBot")
POLL_INTERVAL_MINUTES = 5
RSS_CHANNELS_KEY = "rss_channels"  # Dict of {guild_id: channel_id}
USER_AGENT = {"User-Agent": "FreesonaBot/1.0"}
# Embed palette
COLOR_NEWS = discord.Color.from_rgb(88, 101, 242)
COLOR_OK = discord.Color.from_rgb(87, 242, 135)
COLOR_WARN = discord.Color.from_rgb(254, 231, 92)
COLOR_ERROR = discord.Color.from_rgb(237, 66, 69)


def _status_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    """Small, consistent embed for command feedback."""
    return discord.Embed(title=title, description=description, color=color)


def _ok(description: str, title: str = "Done") -> discord.Embed:
    return _status_embed(title, description, COLOR_OK)


def _warn(description: str, title: str = "Notice") -> discord.Embed:
    return _status_embed(title, description, COLOR_WARN)


def _error(description: str, title: str = "Error") -> discord.Embed:
    return _status_embed(title, description, COLOR_ERROR)


async def feed_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    current = current.lower()
    choices = [
        app_commands.Choice(name=name, value=name)
        for name in sorted(load_rss_feeds())
        if current in name
    ]
    return choices[:25]


def _resolve_link(item, feed_url: str) -> None:
    """Resolve a relative item link against the feed's URL (in place)."""
    if item.link and not urlparse(item.link).netloc:
        item.link = urljoin(feed_url, item.link)


class NewsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_feeds.start()

    async def cog_unload(self):
        self.poll_feeds.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_news_embed(item, name: str) -> discord.Embed:
        """Standardized embed builder for news articles."""
        # Deduplicate title and summary (Nitter feeds often put tweet text
        # in both).
        title = item.title[:256]
        summary = item.summary[:400] if item.summary else ""
        # If the summary starts with the title (ignoring trailing
        # punctuation/whitespace on the title), strip the duplicate part.
        if summary and title:
            title_stripped = title.rstrip(" .,;:!?")
            if summary.startswith(title_stripped):
                summary = summary[len(title_stripped) :]
                summary = summary.lstrip().lstrip(".,;:!?\n\t")
            elif summary.startswith(title):
                summary = summary[len(title) :]
                summary = summary.lstrip().lstrip(".,;:!?\n\t")
        # Quote-style summary reads cleanly under the title
        if summary:
            summary = "\n".join(
                f"> {line}" if line.strip() else ">" for line in summary.splitlines()
            )
        embed = discord.Embed(
            title=title,
            url=item.link,
            description=summary or None,
            color=COLOR_NEWS,
        )
        # Author line: byline if present, otherwise the feed name
        embed.set_author(name=(item.author or name)[:256])
        if item.image_url:
            embed.set_image(url=item.image_url)
        footer_text = name
        if item.published:
            footer_text += f"  \u2022  {item.published}"
        embed.set_footer(text=footer_text)
        return embed

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------
    @tasks.loop(minutes=POLL_INTERVAL_MINUTES)
    async def poll_feeds(self):
        await self.bot.wait_until_ready()
        config = load_config()
        rss_channels = config.get(RSS_CHANNELS_KEY, {})
        if not rss_channels:
            return
        feeds = load_rss_feeds(config)
        seen = load_seen_links(config)
        new_links: list[str] = []
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        ) as session:
            for name, url in feeds.items():
                try:
                    async with session.get(url, headers=USER_AGENT) as resp:
                        if resp.status >= 400:
                            logger.warning(
                                "RSS poll: %s returned HTTP %s",
                                name,
                                resp.status,
                            )
                            continue
                        xml_text = await resp.text()
                    items = parse_feed(xml_text, limit=10)
                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    ValueError,
                ) as e:
                    logger.warning("RSS poll error for %s: %s", name, e)
                    continue
                for item in items:
                    if not item.link:
                        continue
                    _resolve_link(item, url)
                    if item.link in seen:
                        continue
                    embed = self._build_news_embed(item, name)
                    posted = False
                    for guild_id_str, channel_id in rss_channels.items():
                        # Ensure channel_id is an int for get_channel
                        channel = self.bot.get_channel(int(channel_id))
                        if not isinstance(channel, discord.TextChannel):
                            continue
                        try:
                            await channel.send(embed=embed)
                            posted = True
                        except discord.Forbidden:
                            logger.error(
                                "RSS: Permission denied in guild %s",
                                guild_id_str,
                            )
                        except discord.HTTPException as e:
                            logger.warning(
                                "RSS: Failed to send item from %s: %s",
                                name,
                                e,
                            )
                    if posted:
                        new_links.append(item.link)
                        seen.add(item.link)
                        await asyncio.sleep(0.5)
        if new_links:
            mark_links_seen(new_links)
            logger.info("RSS: posted %s new article(s)", len(new_links))

    @poll_feeds.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    @commands.hybrid_group(
        name="rss",
        help="Read and manage RSS news feeds.",
    )
    async def rss_group(self, ctx):
        embed = discord.Embed(
            title="RSS News Feeds",
            description="Read feeds on demand or have new articles posted automatically.",
            color=COLOR_NEWS,
        )
        embed.add_field(
            name="Reading",
            value=(
                "`/rss list`  \u2013  show all feeds\n"
                "`/rss latest <feed> [limit]`  \u2013  show recent articles"
            ),
            inline=False,
        )
        embed.add_field(
            name="Admin",
            value=(
                "`/rss add <name> <url>`  \u2013  add or update a feed\n"
                "`/rss remove <name>`  \u2013  remove a feed\n"
                "`/rss setchannel <channel>`  \u2013  set the auto-post channel\n"
                "`/rss clearchannel`  \u2013  stop auto-posting"
            ),
            inline=False,
        )
        await ctx.send(embed=embed, ephemeral=bool(ctx.interaction))

    @rss_group.command(
        name="setchannel", help="Set the channel for auto-posts (Admin only)."
    )
    @commands.has_permissions(administrator=True)
    async def rss_setchannel(self, ctx, channel: discord.TextChannel):
        config = load_config()
        channels = config.setdefault(RSS_CHANNELS_KEY, {})
        channels[str(ctx.guild.id)] = channel.id
        save_config(config)
        await ctx.send(
            embed=_ok(
                f"New articles will be posted to {channel.mention}.",
                "Auto-post channel set",
            ),
            ephemeral=True,
        )

    @rss_group.command(name="clearchannel", help="Stop auto-posting RSS (Admin only).")
    @commands.has_permissions(administrator=True)
    async def rss_clearchannel(self, ctx):
        config = load_config()
        channels = config.get(RSS_CHANNELS_KEY, {})
        if str(ctx.guild.id) in channels:
            del channels[str(ctx.guild.id)]
            save_config(config)
            await ctx.send(
                embed=_ok(
                    "New articles will no longer be posted.", "Auto-post disabled"
                ),
                ephemeral=True,
            )
        else:
            await ctx.send(
                embed=_warn("No auto-post channel is configured for this server."),
                ephemeral=True,
            )

    @rss_group.command(name="list", help="List all configured RSS feeds.")
    async def rss_list(self, ctx):
        config = load_config()
        feeds = load_rss_feeds(config)
        channels = config.get(RSS_CHANNELS_KEY, {})
        channel_id = channels.get(str(ctx.guild.id))
        channel_mention = f"<#{channel_id}>" if channel_id else "Not set"
        # Build the description line by line so it never gets cut mid-entry
        description = ""
        for name, url in sorted(feeds.items()):
            entry = f"**{name}**\n-# {url}\n\n"
            if len(description) + len(entry) > 4000:
                description += "*...and more*"
                break
            description += entry
        embed = discord.Embed(
            title="RSS Feeds",
            description=description.strip() or "No feeds configured.",
            color=COLOR_NEWS,
        )
        embed.add_field(name="Feeds", value=str(len(feeds)), inline=True)
        embed.add_field(name="Auto-post channel", value=channel_mention, inline=True)
        embed.set_footer(text=f"Checked every {POLL_INTERVAL_MINUTES} minutes")
        await ctx.send(embed=embed, ephemeral=True)

    @rss_group.command(name="latest", help="Show latest items from an RSS feed.")
    @app_commands.autocomplete(name=feed_autocomplete)
    async def rss_latest(self, ctx, name: str, limit: int = 5):
        feeds = load_rss_feeds()
        key = name.lower().strip()
        url = feeds.get(key)
        if not url:
            await ctx.send(
                embed=_error(f"No feed named `{key}` exists.", "Unknown feed"),
                ephemeral=True,
            )
            return
        limit = max(1, min(limit, 10))
        await ctx.defer(ephemeral=False)
        try:
            async with (
                aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as session,
                session.get(url, headers=USER_AGENT) as resp,
            ):
                if resp.status >= 400:
                    await ctx.send(
                        embed=_error(
                            f"The feed responded with HTTP {resp.status}.",
                            "Feed unavailable",
                        )
                    )
                    return
                xml_text = await resp.text()
            items = parse_feed(xml_text, limit=limit)
            for item in items:
                _resolve_link(item, url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            await ctx.send(
                embed=_error(f"Could not read `{key}`.\n```{e}```"[:4096], "Feed error")
            )
            return
        if not items:
            await ctx.send(
                embed=_warn("This feed has no items right now.", "Nothing to show")
            )
            return
        embeds = [self._build_news_embed(item, key) for item in items]
        await ctx.send(embeds=embeds)

    @rss_group.command(name="add", help="Add or update an RSS feed (Admin only).")
    @commands.has_permissions(administrator=True)
    async def rss_add(self, ctx, name: str, url: str):
        key = name.lower().strip()
        if not key.replace("-", "").replace("_", "").isalnum():
            await ctx.send(
                embed=_error(
                    "Names may only contain letters, numbers, hyphens and underscores.",
                    "Invalid name",
                ),
                ephemeral=True,
            )
            return
        if not is_public_http_url(url):
            await ctx.send(
                embed=_error("Provide a public http(s) URL.", "Invalid URL"),
                ephemeral=True,
            )
            return
        save_rss_feed(key, url)
        await ctx.send(embed=_ok(f"**{key}**\n-# {url}", "Feed saved"), ephemeral=True)

    @rss_group.command(name="remove", help="Remove an RSS feed (Admin only).")
    @commands.has_permissions(administrator=True)
    @app_commands.autocomplete(name=feed_autocomplete)
    async def rss_remove(self, ctx, name: str):
        key = name.lower().strip()
        if delete_rss_feed(key):
            await ctx.send(
                embed=_ok(f"`{key}` was removed.", "Feed removed"), ephemeral=True
            )
        else:
            await ctx.send(
                embed=_error(f"No feed named `{key}` exists.", "Not found"),
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(NewsCog(bot))
