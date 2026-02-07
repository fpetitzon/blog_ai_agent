"""Discover new blogs similar to the ones the user already follows.

Uses Substack's public API to find recommended/related publications,
and scrapes blogroll links from WordPress blogs.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from blog_agent import USER_AGENT
from blog_agent.models import FeedSource, normalize_url

logger = logging.getLogger(__name__)

# Domains that are never blogs
_NON_BLOG_DOMAINS = frozenset(
    {
        "twitter.com",
        "x.com",
        "facebook.com",
        "youtube.com",
        "instagram.com",
        "linkedin.com",
        "amazon.com",
        "wikipedia.org",
        "github.com",
    }
)


def discover_substack_recommendations(
    source: FeedSource,
    timeout: int = 15,
) -> list[FeedSource]:
    """Find recommended Substack publications from a given blog.

    Substack publications expose recommendations at /recommendations
    on their site.
    """
    url = source.url.rstrip("/")

    # Only works for Substack-hosted blogs
    if "substack.com" not in url and not _is_custom_substack(url, timeout):
        return []

    recommendations: list[FeedSource] = []

    try:
        resp = httpx.get(
            f"{url}/recommendations",
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.select("a[href*='substack.com']"):
                href = link.get("href", "")
                name = link.get_text(strip=True)
                if _is_valid_substack_url(href) and name:
                    rec = FeedSource(
                        name=name,
                        url=href.rstrip("/"),
                        feed_url=f"{href.rstrip('/')}/feed",
                        tags=["discovered"],
                    )
                    recommendations.append(rec)
    except httpx.HTTPError as exc:
        logger.debug(
            "Could not fetch recommendations for %s: %s",
            source.name,
            exc,
        )

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[FeedSource] = []
    for rec in recommendations:
        key = normalize_url(rec.url)
        if key not in seen:
            seen.add(key)
            unique.append(rec)

    logger.info(
        "Discovered %d recommendations from %s",
        len(unique),
        source.name,
    )
    return unique


def _is_custom_substack(url: str, timeout: int = 10) -> bool:
    """Check if a URL is a custom-domain Substack."""
    try:
        resp = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        return "substackcdn.com" in resp.text or "substack-post" in resp.text
    except httpx.HTTPError:
        return False


def _is_valid_substack_url(url: str) -> bool:
    """Check if a URL looks like a Substack publication root."""
    if not url or not url.startswith("http"):
        return False
    if "/p/" in url or "/s/" in url:
        return False
    return "substack.com" in url


def discover_blogroll_links(
    source: FeedSource,
    timeout: int = 15,
) -> list[FeedSource]:
    """Discover related blogs from WordPress blogroll/links pages."""
    url = source.url.rstrip("/")
    discovered: list[FeedSource] = []

    blogroll_paths = ["/blogroll", "/links", "/recommended", "/friends"]

    for path in blogroll_paths:
        try:
            resp = httpx.get(
                f"{url}{path}",
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.select("article a[href], .entry-content a[href]"):
                href = link.get("href", "")
                name = link.get_text(strip=True)
                if (
                    href.startswith("http")
                    and name
                    and len(name) > 2
                    and _looks_like_blog(href)
                ):
                    discovered.append(
                        FeedSource(
                            name=name,
                            url=href.rstrip("/"),
                            tags=["discovered", "blogroll"],
                        )
                    )
        except httpx.HTTPError:
            continue

    logger.info(
        "Discovered %d blogroll links from %s",
        len(discovered),
        source.name,
    )
    return discovered


def _looks_like_blog(url: str) -> bool:
    """Heuristic: does this URL look like a blog homepage?"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")
    if domain in _NON_BLOG_DOMAINS:
        return False
    if parsed.path.count("/") > 2:
        return False
    return True


def discover_related_feeds(
    sources: list[FeedSource],
    timeout: int = 15,
) -> list[FeedSource]:
    """Run all discovery methods and return new feeds.

    Deduplicates against the existing sources.
    """
    existing_urls = {normalize_url(s.url) for s in sources}
    all_discovered: list[FeedSource] = []

    for source in sources:
        recs = discover_substack_recommendations(source, timeout)
        all_discovered.extend(recs)

        blogroll = discover_blogroll_links(source, timeout)
        all_discovered.extend(blogroll)

    # Deduplicate and filter out already-known sources
    seen: set[str] = set(existing_urls)
    unique: list[FeedSource] = []
    for feed in all_discovered:
        key = normalize_url(feed.url)
        if key not in seen:
            seen.add(key)
            unique.append(feed)

    logger.info("Total newly discovered feeds: %d", len(unique))
    return unique
