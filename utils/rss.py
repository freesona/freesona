#!/usr/bin/env python3
# utils/rss.py: RSS/Atom parsing and feed config helpers.

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from xml.etree import ElementTree

from utils.config import load_config, save_config

logger = logging.getLogger(__name__)

# RDF namespace constant
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

RSS_FEEDS_KEY = "rss_feeds"
RSS_SEEN_KEY = "rss_seen"  # list of seen article links, persisted in config.json
RSS_DISABLED_KEY = "rss_disabled"  # built-in feeds the user has explicitly removed

DEFAULT_RSS_FEEDS: dict[str, str] = {
    "bbc-world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "bbc-tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "npr-news": "https://feeds.npr.org/1001/rss.xml",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "dw-world": "https://rss.dw.com/rdf/rss-en-all",
}

SEEN_CAP = 500  # max links to remember; oldest are evicted

SHORT_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:reut\.rs|t\.co|bit\.ly|tinyurl\.com|goo\.gl|ow\.ly|"
    r"is\.gd|buff\.ly|adf\.ly|bit\.do|short\.io|cutt\.ly|v\.gd|tr\.im|"
    r"u\.nu|yourls\.org)/[a-zA-Z0-9]+"
)

STRIP_CHARS = " .,;:!?\n\t"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class FeedItem:
    title: str
    link: str
    published: str = ""
    summary: str = ""
    author: str = ""
    image_url: str = ""


class _ImageURLExtractor(HTMLParser):
    """HTML parser to extract the first image URL from HTML content."""

    def __init__(self) -> None:
        super().__init__()
        self.image_url: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "img" and not self.image_url:
            for name, value in attrs:
                if name == "src" and value:
                    self.image_url = value
                    break


def extract_image_url_from_html(html_text: str) -> str:
    """Extract the first image URL from HTML content using an HTML parser."""
    if not html_text:
        return ""
    parser = _ImageURLExtractor()
    parser.feed(html_text)
    return parser.image_url


# ---------------------------------------------------------------------------
# Feed CRUD
# ---------------------------------------------------------------------------


def load_rss_feeds(config: dict | None = None) -> dict[str, str]:
    config = config or load_config()
    disabled = set(config.get(RSS_DISABLED_KEY, []))
    feeds = {k: v for k, v in DEFAULT_RSS_FEEDS.items() if k not in disabled}

    saved = config.get(RSS_FEEDS_KEY, {})
    if isinstance(saved, dict):
        for name, url in saved.items():
            if isinstance(name, str) and isinstance(url, str) and url.strip():
                feeds[name.lower().strip()] = url.strip()
    return feeds


def save_rss_feed(name: str, url: str) -> None:
    config = load_config()
    key = name.lower().strip()

    # If re-adding a previously disabled built-in, un-disable it
    disabled: list = config.setdefault(RSS_DISABLED_KEY, [])
    if key in disabled:
        disabled.remove(key)

    feeds = config.setdefault(RSS_FEEDS_KEY, {})
    feeds[key] = url.strip()
    save_config(config)


def delete_rss_feed(name: str) -> bool:
    """
    Remove a feed. Built-in feeds are added to a disabled list rather than
    truly deleted (since they live in code, not config). Custom feeds are
    removed from config entirely. Returns True if anything was removed.
    """
    config = load_config()
    key = name.lower().strip()
    changed = False

    # Remove from custom feeds if present
    feeds = config.setdefault(RSS_FEEDS_KEY, {})
    if key in feeds:
        del feeds[key]
        changed = True

    # Disable built-in feeds
    if key in DEFAULT_RSS_FEEDS:
        disabled: list = config.setdefault(RSS_DISABLED_KEY, [])
        if key not in disabled:
            disabled.append(key)
        changed = True

    if changed:
        save_config(config)
    return changed


# ---------------------------------------------------------------------------
# Seen-link tracking (deduplication for auto-posting)
# ---------------------------------------------------------------------------


def load_seen_links(config: dict | None = None) -> set[str]:
    config = config or load_config()
    return set(config.get(RSS_SEEN_KEY, []))


def mark_links_seen(links: list[str]) -> None:
    if not links:
        return

    config = load_config()
    seen: list = config.setdefault(RSS_SEEN_KEY, [])
    for link in links:
        if link and link not in seen:
            seen.append(link)

    # Evict oldest entries beyond cap
    config[RSS_SEEN_KEY] = seen[-SEEN_CAP:] if len(seen) > SEEN_CAP else seen
    save_config(config)


# ---------------------------------------------------------------------------
# Text cleanup helpers
# ---------------------------------------------------------------------------


def _deduplicate_short_urls(text: str) -> str:
    """Remove duplicate short URLs (like reut.rs/xxx) from text.

    Nitter feeds often duplicate short URLs in titles and descriptions.
    """
    matches = list(SHORT_URL_PATTERN.finditer(text))
    if len(matches) <= 1:
        return text

    # Keep only the first occurrence of each unique URL (normalized to
    # include the protocol).
    seen_urls: set[str] = set()
    result = text
    for match in reversed(matches):
        url = match.group(0)
        normalized = url if url.startswith("http") else "https://" + url
        if normalized in seen_urls:
            start, end = match.span()
            result = result[:start] + result[end:]
        else:
            seen_urls.add(normalized)

    return result


def _clean_title_and_summary(title: str, summary: str) -> tuple[str, str]:
    """Clean title and summary by removing duplicates.

    Nitter feeds often have:
    - Duplicate short URLs in title
    - Title repeated at the start of summary (with or without "Link " prefix)
    """
    title = _deduplicate_short_urls(title)

    if summary and title:
        title_stripped = title.rstrip(" .,;:!?")
        for prefix in (
            title_stripped,
            title,
            "Link " + title_stripped,  # Nitter format
            "Link " + title,
        ):
            if summary.startswith(prefix):
                summary = summary[len(prefix) :].lstrip(STRIP_CHARS)
                break

    return title, _deduplicate_short_urls(summary)


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError, OverflowError):
        return value


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def _local_tag(node: ElementTree.Element) -> str:
    """Lowercased tag name with any XML namespace stripped."""
    return node.tag.rsplit("}", 1)[-1].lower()


def child_text(node: ElementTree.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        if _local_tag(child) in names and child.text:
            return child.text.strip()
    return ""


def child_attr(node: ElementTree.Element, name: str, attr: str) -> str:
    for child in list(node):
        if _local_tag(child) == name:
            value = child.attrib.get(attr)
            if value:
                return value.strip()
    return ""


def _find_image_url(node: ElementTree.Element) -> str:
    """Pick the best image from media:content/thumbnail/enclosure children."""
    image_url = ""
    max_width = 0

    for child in list(node):
        tag = _local_tag(child)

        if tag in ("content", "thumbnail") and "url" in child.attrib:
            url = child.attrib["url"].strip()
            try:
                width = int(child.attrib.get("width", 0))
            except ValueError:
                logger.debug(
                    "Invalid width attribute for image: %s",
                    child.attrib.get("width"),
                )
                width = 0
            if width >= max_width:
                max_width = width
                image_url = url

        elif tag == "enclosure" and "url" in child.attrib:
            type_attr = child.attrib.get("type", "")
            if not image_url or "image" in type_attr:
                image_url = child.attrib["url"].strip()

    return image_url


def _build_item(
    node: ElementTree.Element,
    title: str,
    link: str,
    published: str,
    summary: str,
    author: str,
) -> FeedItem:
    """Shared cleanup and assembly for RSS, Atom and RDF items."""
    title = strip_html(title)
    summary = strip_html(summary)
    title, summary = _clean_title_and_summary(title, summary)

    image_url = _find_image_url(node) or extract_image_url_from_html(summary)

    return FeedItem(
        title=title,
        link=link,
        published=normalize_date(published),
        summary=summary,
        author=strip_html(author),
        image_url=image_url,
    )


def _is_reply(title: str) -> bool:
    return title.lower().startswith(("r to @", "re:"))


# ---------------------------------------------------------------------------
# Format-specific parsers
# ---------------------------------------------------------------------------


def _parse_rdf_feed(root: ElementTree.Element, limit: int = 5) -> list[FeedItem]:
    """Parse RDF (RSS 1.0) format feeds."""
    channel = next((c for c in root if _local_tag(c) == "channel"), None)
    if channel is None:
        return []

    # Collect rdf:resource links from channel/items/Seq/li
    item_urls: list[str] = []
    for items_node in channel:
        if _local_tag(items_node) != "items":
            continue
        for seq in items_node:
            if _local_tag(seq) != "seq":
                continue
            for li in seq:
                if _local_tag(li) == "li":
                    resource = li.attrib.get(f"{{{RDF_NS}}}resource")
                    if resource:
                        item_urls.append(resource)

    # Now find item elements with matching rdf:about
    items: list[FeedItem] = []
    for child in root:
        if _local_tag(child) != "item":
            continue

        about = child.attrib.get(f"{{{RDF_NS}}}about")

        title = child_text(child, ("title",)) or "(untitled)"
        if _is_reply(title):
            continue

        if about in item_urls and len(items) >= limit:
            break

        link = child_text(child, ("link",)) or about or ""
        published = child_text(
            child,
            ("date", "dc:date", "dc.date", "pubdate", "published", "updated"),
        )
        summary = child_text(child, ("description", "summary", "content"))
        author = child_text(child, ("creator", "author", "dc:creator", "dc.creator"))

        items.append(_build_item(child, title, link, published, summary, author))

    return items


def parse_feed(xml_text: str, limit: int = 5) -> list[FeedItem]:
    root = ElementTree.fromstring(xml_text)
    root_tag = _local_tag(root)

    # RDF (RSS 1.0)
    if root_tag == "rdf":
        return _parse_rdf_feed(root, limit)

    # RSS 2.0 uses <item>, Atom uses <entry>
    if root_tag == "rss":
        channel = next((c for c in root.iter() if _local_tag(c) == "channel"), root)
        nodes = [c for c in channel if _local_tag(c) == "item"]
    else:
        nodes = [c for c in root if _local_tag(c) == "entry"]

    items: list[FeedItem] = []
    for node in nodes:
        if len(items) >= limit:
            break

        title = child_text(node, ("title",)) or "(untitled)"
        if _is_reply(title):
            continue

        link = child_text(node, ("link",)) or child_attr(node, "link", "href")
        published = child_text(node, ("pubdate", "published", "updated"))
        summary = child_text(node, ("description", "summary", "content"))
        author = child_text(node, ("creator", "author"))

        items.append(_build_item(node, title, link, published, summary, author))

    return items
