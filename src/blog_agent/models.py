"""Data models for blog posts and feed sources."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FeedType(str, Enum):
    RSS = "rss"
    ATOM = "atom"
    HTML_SCRAPE = "html_scrape"


class FeedSource(BaseModel):
    """A blog or feed source to monitor."""

    name: str
    url: str
    feed_url: str | None = None
    feed_type: FeedType = FeedType.RSS
    tags: list[str] = Field(default_factory=list)

    # Per-source limits for prolific authors
    max_posts: int | None = None  # None = no limit
    min_comments: int | None = None  # None = no minimum

    def get_feed_url(self) -> str:
        """Return the feed URL, falling back to common patterns."""
        if self.feed_url:
            return self.feed_url
        # Try common RSS feed URL patterns
        base = self.url.rstrip("/")
        return f"{base}/feed"


class BlogPost(BaseModel):
    """A single blog post."""

    title: str
    author: str
    url: str
    published: datetime | None = None
    summary: str = ""
    likes: int | None = None
    comments: int | None = None
    source_name: str = ""
    is_read: bool = False

    def age_days(self) -> int | None:
        """Return the age of the post in days, or None if no publish date."""
        if self.published is None:
            return None
        delta = datetime.now(tz=self.published.tzinfo) - self.published
        return delta.days

    def short_summary(self, max_length: int = 120) -> str:
        """Return a truncated summary."""
        if len(self.summary) <= max_length:
            return self.summary
        return self.summary[: max_length - 3] + "..."


# Default feed sources - the blogs the user likes
DEFAULT_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Marginal Revolution",
        url="https://marginalrevolution.com/",
        feed_url="https://marginalrevolution.com/feed",
        tags=["economics", "culture"],
        max_posts=5,
        min_comments=50,
    ),
    FeedSource(
        name="Bet On It (Bryan Caplan)",
        url="https://www.betonit.ai/",
        feed_url="https://www.betonit.ai/feed",
        tags=["economics", "prediction"],
    ),
    FeedSource(
        name="Cremieux Recueil",
        url="https://www.cremieux.xyz/",
        feed_url="https://www.cremieux.xyz/feed",
        tags=["data", "science", "statistics"],
    ),
    FeedSource(
        name="Astral Codex Ten",
        url="https://www.astralcodexten.com/",
        feed_url="https://www.astralcodexten.com/feed",
        tags=["rationality", "science", "culture"],
    ),
    FeedSource(
        name="A Collection of Unmitigated Pedantry",
        url="https://acoup.blog/",
        feed_url="https://acoup.blog/feed/",
        tags=["history", "military", "culture"],
    ),
    FeedSource(
        name="The Zvi",
        url="https://thezvi.substack.com/",
        feed_url="https://thezvi.substack.com/feed",
        tags=["rationality", "AI", "culture"],
    ),
    FeedSource(
        name="Derek Thompson",
        url="https://www.derekthompson.org/",
        feed_url="https://www.derekthompson.org/feed",
        tags=["culture", "economics", "media"],
    ),
]
