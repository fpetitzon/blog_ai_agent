"""Discover new blogs similar to the ones the user already follows.

Uses Substack's public API to find recommended/related publications,
and scrapes blogroll links from WordPress blogs.
"""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from blog_agent.models import FeedSource

logger = logging.getLogger(__name__)

# Substack API endpoint for publication recommendations
_SUBSTACK_API = "https://substack.com/api/v1"


def discover_substack_recommendations(
    source: FeedSource,
    timeout: int = 15,
) -> list[FeedSource]:
    """Find recommended Substack publications from a given Substack blog.

    Substack publications expose recommendations at /recommendations on
    their site, and via an API endpoint.
    """
    url = source.url.rstrip("/")

    # Only works for Substack-hosted blogs
    if "substack.com" not in url and not _is_custom_substack(url, timeout):
        return []

    recommendations: list[FeedSource] = []

    # Try the recommendations page
    try:
        resp = httpx.get(
            f"{url}/recommendations",
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "BlogAgent/0.1"},
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Look for recommendation links
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
        logger.debug("Could not fetch recommendations for %s: %s", source.name, exc)

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[FeedSource] = []
    for rec in recommendations:
        normalized = rec.url.rstrip("/").lower()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(rec)

    logger.info("Discovered %d recommendations from %s", len(unique), source.name)
    return unique


def _is_custom_substack(url: str, timeout: int = 10) -> bool:
    """Check if a URL is a custom-domain Substack by looking for markers."""
    try:
        resp = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "BlogAgent/0.1"},
        )
        # Substack pages contain distinctive markers
        return "substackcdn.com" in resp.text or "substack-post" in resp.text
    except httpx.HTTPError:
        return False


def _is_valid_substack_url(url: str) -> bool:
    """Check if a URL looks like a Substack publication root."""
    if not url or not url.startswith("http"):
        return False
    # Filter out individual post URLs, assets, etc.
    if "/p/" in url or "/s/" in url:
        return False
    if "substack.com" in url:
        return True
    return False


def discover_blogroll_links(
    source: FeedSource,
    timeout: int = 15,
) -> list[FeedSource]:
    """Discover related blogs from WordPress blogroll/links pages."""
    url = source.url.rstrip("/")
    discovered: list[FeedSource] = []

    # Common blogroll page patterns
    blogroll_paths = ["/blogroll", "/links", "/recommended", "/friends"]

    for path in blogroll_paths:
        try:
            resp = httpx.get(
                f"{url}{path}",
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "BlogAgent/0.1"},
            )
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Look for external links in the main content area
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

    logger.info("Discovered %d blogroll links from %s", len(discovered), source.name)
    return discovered


def _looks_like_blog(url: str) -> bool:
    """Heuristic: does this URL look like a blog homepage?"""
    # Reject common non-blog domains
    non_blog = {
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
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")
    if domain in non_blog:
        return False
    # Should be roughly a homepage (short path)
    if parsed.path.count("/") > 2:
        return False
    return True


def discover_related_feeds(
    sources: list[FeedSource],
    timeout: int = 15,
) -> list[FeedSource]:
    """Run all discovery methods across all sources and return new feeds.

    Deduplicates against the existing sources.
    """
    existing_urls = {s.url.rstrip("/").lower() for s in sources}
    all_discovered: list[FeedSource] = []

    for source in sources:
        # Substack recommendations
        recs = discover_substack_recommendations(source, timeout)
        all_discovered.extend(recs)

        # Blogroll links
        blogroll = discover_blogroll_links(source, timeout)
        all_discovered.extend(blogroll)

    # Deduplicate and filter out already-known sources
    seen: set[str] = set(existing_urls)
    unique: list[FeedSource] = []
    for feed in all_discovered:
        key = feed.url.rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            unique.append(feed)

    logger.info("Total newly discovered feeds: %d", len(unique))
    return unique
