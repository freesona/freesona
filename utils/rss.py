# utils/rss.py: RSS/Atom parsing and feed config helpers.
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from utils.config import load_config, save_config

logger = logging.getLogger(__name__)

# RDF namespace constant
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


class _ImageURLExtractor(HTMLParser):
    """HTML parser to extract the first image URL from HTML content."""

    def __init__(self) -> None:
        super().__init__()
        self.image_url: str = ""

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() == "img" and not self.image_url:
            for name, value in attrs:
                if name == "src" and value:
                    self.image_url = value
                    break


def extract_image_url_from_html(html_text: str) -> str:
    """Extract the first image URL from HTML content using a proper HTML parser."""
    if not html_text:
        return ""
    parser = _ImageURLExtractor()
    parser.feed(html_text)
    return parser.image_url


RSS_FEEDS_KEY = "rss_feeds"
RSS_SEEN_KEY = (
    "rss_seen"  # set of seen article links, persisted in config.json
)
# built-in feeds the user has explicitly removed
RSS_DISABLED_KEY = "rss_disabled"

DEFAULT_RSS_FEEDS: dict[str, str] = {
    "bbc-world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "bbc-tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "npr-news": "https://feeds.npr.org/1001/rss.xml",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "dw-world": "https://rss.dw.com/rdf/rss-en-all",
}


@dataclass
class FeedItem:
    title: str
    link: str
    published: str = ""
    summary: str = ""
    author: str = ""
    image_url: str = ""


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
    # If re-adding a previously disabled built-in, un-disable it
    disabled: list = config.setdefault(RSS_DISABLED_KEY, [])
    key = name.lower().strip()
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

SEEN_CAP = 500  # max links to remember; oldest are evicted


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
    if len(seen) > SEEN_CAP:
        config[RSS_SEEN_KEY] = seen[-SEEN_CAP:]
    else:
        config[RSS_SEEN_KEY] = seen
    save_config(config)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def _deduplicate_short_urls(text: str) -> str:
    """Remove duplicate short URLs (like reut.rs/xxx) from text.

    Nitter feeds often duplicate short URLs in titles and descriptions.
    """
    # Pattern to match short URLs with or without protocol
    url_pattern = r"(?:https?://)?(?:reut\.rs|t\.co|bit\.ly|tinyurl\.com|goo\.gl|ow\.ly|is\.gd|buff\.ly|adf\.ly|bit\.do|short\.io|cutt\.ly|v\.gd|tr\.im|u\.nu|yourls\.org)/[a-zA-Z0-9]+"
    matches = list(re.finditer(url_pattern, text))
    if len(matches) <= 1:
        return text

    # Keep only the first occurrence of each unique URL (normalized to include
    # protocol)
    seen_urls = set()
    result = text
    for match in reversed(matches):
        url = match.group(0)
        # Normalize URL for comparison (add protocol if missing)
        normalized = url if url.startswith("http") else "http://" + url
        if normalized in seen_urls:
            # Remove this duplicate occurrence
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
    # Remove duplicate short URLs from title
    title = _deduplicate_short_urls(title)

    # If summary starts with title (or title without trailing punctuation),
    # strip it
    if summary and title:
        title_stripped = title.rstrip(" .,;:!?")
        # Check if summary starts with title
        if summary.startswith(title_stripped):
            summary = summary[len(title_stripped):].lstrip(" .,;:!?\n\t")
        elif summary.startswith(title):
            summary = summary[len(title):].lstrip(" .,;:!?\n\t")
        # Check if summary starts with "Link " + title (Nitter format)
        elif summary.startswith("Link " + title_stripped):
            summary = summary[len("Link " + title_stripped):].lstrip(
                " .,;:!?\n\t"
            )
        elif summary.startswith("Link " + title):
            summary = summary[len("Link " + title):].lstrip(" .,;:!?\n\t")

    # Also deduplicate URLs in summary
    summary = _deduplicate_short_urls(summary)

    return title, summary


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def child_text(node: ElementTree.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names and child.text:
            return child.text.strip()
    return ""


def child_attr(node: ElementTree.Element, name: str, attr: str) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag == name:
            value = child.attrib.get(attr)
            if value:
                return value.strip()
    return ""


def normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError, OverflowError):
        return value


def _parse_rdf_feed(
    root: ElementTree.Element, limit: int = 5
) -> list[FeedItem]:
    """Parse RDF (RSS 1.0) format feeds."""
    # Find channel element to get item references
    channel = None
    for child in root:
        if child.tag.rsplit("}", 1)[-1].lower() == "channel":
            channel = child
            break

    if channel is None:
        return []

    # Find items/Seq/li elements with rdf:resource attributes
    item_urls = []
    for child in channel:
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag == "items":
            for seq_child in child:
                seq_tag = seq_child.tag.rsplit("}", 1)[-1].lower()
                if seq_tag == "seq":
                    for li in seq_child:
                        li_tag = li.tag.rsplit("}", 1)[-1].lower()
                        if li_tag == "li":
                            resource = li.attrib.get(f"{{{RDF_NS}}}resource")
                            if resource:
                                item_urls.append(resource)

    # Now find item elements with matching rdf:about
    items: list[FeedItem] = []
    for child in root:
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag == "item":
            about = child.attrib.get(f"{{{RDF_NS}}}about")

            title = child_text(child, ("title",)) or "(untitled)"
            if title.lower().startswith(("r to @", "re:")):
                continue

            if about in item_urls and len(items) >= limit:
                break

            link = child_text(child, ("link",)) or about or ""
            published = child_text(
                child,
                (
                    "date",
                    "dc:date",
                    "dc.date",
                    "pubdate",
                    "published",
                    "updated",
                ),
            )
            summary = child_text(child, ("description", "summary", "content"))
            author = child_text(
                child, ("creator", "author", "dc:creator", "dc.creator")
            )

            # Strip HTML from title and summary first
            title = strip_html(title)
            summary = strip_html(summary)

            # Clean title and summary (deduplicate URLs and title repetition)
            title, summary = _clean_title_and_summary(title, summary)

            # Extract Image
            image_url = ""
            max_width = 0

            for subchild in list(child):
                sub_tag = subchild.tag.rsplit("}", 1)[-1].lower()
                if (
                    sub_tag in ("content", "thumbnail")
                    and "url" in subchild.attrib
                ):
                    url = subchild.attrib["url"].strip()
                    try:
                        width = int(subchild.attrib.get("width", 0))
                    except ValueError:
                        logger.debug(f"Invalid width attribute for image: {
                            subchild.attrib.get('width')}")
                        width = 0
                    if width >= max_width:
                        max_width = width
                        image_url = url
                elif sub_tag == "enclosure" and "url" in subchild.attrib:
                    type_attr = subchild.attrib.get("type", "")
                    if not image_url or "image" in type_attr:
                        image_url = subchild.attrib["url"].strip()

            if not image_url:
                image_url = extract_image_url_from_html(summary)

            items.append(
                FeedItem(
                    title=strip_html(title),
                    link=link,
                    published=normalize_date(published),
                    summary=strip_html(summary),
                    author=strip_html(author),
                    image_url=image_url,
                )
            )

    return items


def parse_feed(xml_text: str, limit: int = 5) -> list[FeedItem]:
    root = ElementTree.fromstring(xml_text)
    root_tag = root.tag.rsplit("}", 1)[-1].lower()

    # Handle RDF (RSS 1.0) feeds
    if root_tag == "rdf":
        return _parse_rdf_feed(root, limit)

    if root_tag == "rss":
        channel = next(
            (
                c
                for c in root.iter()
                if c.tag.rsplit("}", 1)[-1].lower() == "channel"
            ),
            root,
        )
        nodes = [
            c
            for c in list(channel)
            if c.tag.rsplit("}", 1)[-1].lower() == "item"
        ]
    else:
        nodes = [
            c
            for c in list(root)
            if c.tag.rsplit("}", 1)[-1].lower() == "entry"
        ]

    items: list[FeedItem] = []
    for node in nodes:
        if len(items) >= limit:
            break

        title = child_text(node, ("title",)) or "(untitled)"
        if title.lower().startswith(("r to @", "re:")):
            continue

        link = child_text(node, ("link",)) or child_attr(node, "link", "href")
        published = child_text(node, ("pubdate", "published", "updated"))
        summary = child_text(node, ("description", "summary", "content"))
        author = child_text(node, ("creator", "author"))

        # Strip HTML from title and summary first
        title = strip_html(title)
        summary = strip_html(summary)

        # Clean title and summary (deduplicate URLs and title repetition)
        title, summary = _clean_title_and_summary(title, summary)

        # Extract Image
        image_url = ""
        max_width = 0

        for child in list(node):
            tag = child.tag.rsplit("}", 1)[-1].lower()
            if tag in ("content", "thumbnail") and "url" in child.attrib:
                url = child.attrib["url"].strip()
                try:
                    width = int(child.attrib.get("width", 0))
                except ValueError:
                    logger.debug(f"Invalid width attribute for image: {
                        child.attrib.get('width')}")
                    width = 0
                if width >= max_width:
                    max_width = width
                    image_url = url
            elif tag == "enclosure" and "url" in child.attrib:
                type_attr = child.attrib.get("type", "")
                if not image_url or "image" in type_attr:
                    image_url = child.attrib["url"].strip()

        if not image_url:
            image_url = extract_image_url_from_html(summary)

        items.append(
            FeedItem(
                title=strip_html(title),
                link=link,
                published=normalize_date(published),
                summary=strip_html(summary),
                author=strip_html(author),
                image_url=image_url,
            )
        )

    return items
