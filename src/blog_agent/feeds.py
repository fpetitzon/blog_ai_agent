"""RSS/Atom feed fetching and parsing."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from time import mktime

import feedparser
import httpx

from blog_agent import USER_AGENT
from blog_agent.models import BlogPost, FeedSource

logger = logging.getLogger(__name__)


def _parse_date(entry: dict) -> datetime | None:
    """Extract a datetime from a feed entry, trying multiple fields."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue

    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw)
            except (TypeError, ValueError):
                pass
            try:
                # ISO 8601 fallback
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                pass
    return None


def _extract_summary(entry: dict) -> str:
    """Extract a text summary from a feed entry."""
    summary = entry.get("summary", "")
    if not summary:
        content_list = entry.get("content", [])
        if content_list and isinstance(content_list, list):
            summary = content_list[0].get("value", "")
    if "<" in summary:
        summary = re.sub(r"<[^>]+>", "", unescape(summary))
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary


_COMMENT_KEYS = ("slash_comments", "thr_total")


def _extract_int_field(entry: dict, keys: tuple[str, ...]) -> int | None:
    """Try to extract an integer value from feed entry metadata.

    Checks the given keys in order, returning the first valid int found.
    """
    for key in keys:
        val = entry.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
    return None


def _extract_likes(entry: dict) -> int | None:
    """Try to extract a like/reaction count from feed metadata."""
    return _extract_int_field(entry, _COMMENT_KEYS)


def _extract_comments(entry: dict) -> int | None:
    """Extract comment count from a feed entry.

    WordPress feeds use the slash:comments namespace which feedparser
    exposes as 'slash_comments'. Atom feeds may use thr:total.
    """
    return _extract_int_field(entry, _COMMENT_KEYS)


def _publish_date_key(post: BlogPost) -> datetime:
    """Sort key for posts: use published date or epoch-min as fallback."""
    return post.published or datetime.min.replace(tzinfo=timezone.utc)


def fetch_feed(
    source: FeedSource, timeout: int = 15, lookback_days: int = 3
) -> list[BlogPost]:
    """Fetch and parse a single RSS/Atom feed, returning recent posts."""
    feed_url = source.get_feed_url()
    logger.info("Fetching feed: %s (%s)", source.name, feed_url)

    try:
        response = httpx.get(
            feed_url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch %s: %s", source.name, exc)
        return []

    feed = feedparser.parse(response.text)

    if feed.bozo and not feed.entries:
        logger.warning(
            "Feed parse error for %s: %s",
            source.name,
            feed.bozo_exception,
        )
        return []

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)

    posts: list[BlogPost] = []
    for entry in feed.entries:
        published = _parse_date(entry)

        if published and published < cutoff:
            continue

        comments = _extract_comments(entry)

        # Apply min_comments filter for prolific sources
        if source.min_comments is not None:
            if comments is None or comments < source.min_comments:
                continue

        post = BlogPost(
            title=entry.get("title", "Untitled"),
            author=entry.get("author", source.name),
            url=entry.get("link", ""),
            published=published,
            summary=_extract_summary(entry),
            likes=_extract_likes(entry),
            comments=comments,
            source_name=source.name,
        )
        posts.append(post)

    # Apply max_posts limit (keep newest first)
    if source.max_posts is not None and len(posts) > source.max_posts:
        posts.sort(key=_publish_date_key, reverse=True)
        posts = posts[: source.max_posts]

    logger.info("Found %d recent posts from %s", len(posts), source.name)
    return posts


def fetch_all_feeds(
    sources: list[FeedSource],
    timeout: int = 15,
    lookback_days: int = 3,
) -> list[BlogPost]:
    """Fetch all feeds and return a combined, sorted list of posts."""
    all_posts: list[BlogPost] = []
    for source in sources:
        posts = fetch_feed(source, timeout=timeout, lookback_days=lookback_days)
        all_posts.extend(posts)

    # Sort by date, newest first; posts without dates go at the end
    all_posts.sort(key=_publish_date_key, reverse=True)
    return all_posts
