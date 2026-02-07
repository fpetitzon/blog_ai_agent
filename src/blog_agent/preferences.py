"""User preference tracking for blog suggestions.

Stores liked/discarded blog preferences in a local JSON file so the agent
can learn which types of blogs the user enjoys and refine future suggestions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from blog_agent.models import FeedSource, normalize_url

logger = logging.getLogger(__name__)

# Default location for the preferences file
DEFAULT_PREFS_PATH = Path.home() / ".config" / "blog-agent" / "preferences.json"


class Preferences(BaseModel):
    """Persisted user preferences for blog suggestions."""

    liked: list[FeedSource] = Field(default_factory=list)
    discarded_urls: list[str] = Field(default_factory=list)

    def is_discarded(self, url: str) -> bool:
        key = normalize_url(url)
        return any(normalize_url(u) == key for u in self.discarded_urls)

    def is_liked(self, url: str) -> bool:
        key = normalize_url(url)
        return any(normalize_url(f.url) == key for f in self.liked)

    def like(self, source: FeedSource) -> None:
        """Add a source to liked list (remove from discarded)."""
        key = normalize_url(source.url)
        self.discarded_urls = [
            u for u in self.discarded_urls if normalize_url(u) != key
        ]
        if not self.is_liked(source.url):
            self.liked.append(source)

    def discard(self, url: str) -> None:
        """Mark a blog URL as discarded (remove from liked)."""
        key = normalize_url(url)
        self.liked = [f for f in self.liked if normalize_url(f.url) != key]
        if not self.is_discarded(url):
            self.discarded_urls.append(url)

    def liked_tags(self) -> dict[str, int]:
        """Return tag frequency counts from liked blogs."""
        counts: dict[str, int] = {}
        for source in self.liked:
            for tag in source.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts


def load_preferences(path: Path | None = None) -> Preferences:
    """Load preferences from disk, returning empty prefs if missing."""
    path = path or DEFAULT_PREFS_PATH
    if not path.exists():
        return Preferences()
    try:
        data = json.loads(path.read_text())
        return Preferences(**data)
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        logger.warning("Could not load preferences from %s: %s", path, exc)
        return Preferences()


def save_preferences(prefs: Preferences, path: Path | None = None) -> None:
    """Save preferences to disk."""
    path = path or DEFAULT_PREFS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prefs.model_dump_json(indent=2))
    logger.debug("Saved preferences to %s", path)


# --- Suggested blogs outside the user's comfort zone ---
# Intentionally diverse to push beyond rationality/economics niche.

SUGGESTED_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Stratechery (Ben Thompson)",
        url="https://stratechery.com",
        feed_url="https://stratechery.com/feed/",
        tags=["tech", "business", "strategy"],
    ),
    FeedSource(
        name="Matt Levine (Money Stuff)",
        url="https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine",
        feed_url="https://newsletterhunt.com/feeds/money-stuff",
        tags=["finance", "law", "humor"],
    ),
    FeedSource(
        name="Construction Physics",
        url="https://www.construction-physics.com",
        feed_url="https://www.construction-physics.com/feed",
        tags=["engineering", "infrastructure", "progress"],
    ),
    FeedSource(
        name="Works in Progress",
        url="https://worksinprogress.co",
        feed_url="https://worksinprogress.co/feed/",
        tags=["progress", "science", "policy"],
    ),
    FeedSource(
        name="Noahpinion",
        url="https://www.noahpinion.blog",
        feed_url="https://www.noahpinion.blog/feed",
        tags=["economics", "policy", "culture"],
    ),
    FeedSource(
        name="Slow Boring (Matt Yglesias)",
        url="https://www.slowboring.com",
        feed_url="https://www.slowboring.com/feed",
        tags=["policy", "politics", "economics"],
    ),
    FeedSource(
        name="Scholars Stage",
        url="https://scholars-stage.org",
        feed_url="https://scholars-stage.org/feed/",
        tags=["geopolitics", "history", "china"],
    ),
    FeedSource(
        name="Dan Luu",
        url="https://danluu.com",
        feed_url="https://danluu.com/atom.xml",
        tags=["tech", "engineering", "systems"],
    ),
    FeedSource(
        name="Palladium Magazine",
        url="https://www.palladiummag.com",
        feed_url="https://www.palladiummag.com/feed/",
        tags=["governance", "philosophy", "civilization"],
    ),
    FeedSource(
        name="Overcoming Bias (Robin Hanson)",
        url="https://www.overcomingbias.com",
        feed_url="https://www.overcomingbias.com/feed",
        tags=["rationality", "economics", "futurism"],
    ),
    FeedSource(
        name="Bits about Money (Patrick McKenzie)",
        url="https://www.bitsaboutmoney.com",
        feed_url="https://www.bitsaboutmoney.com/feed/",
        tags=["finance", "infrastructure", "tech"],
    ),
    FeedSource(
        name="The Intrinsic Perspective",
        url="https://www.theintrinsicperspective.com",
        feed_url="https://www.theintrinsicperspective.com/feed",
        tags=["neuroscience", "consciousness", "culture"],
    ),
    FeedSource(
        name="Experimental History",
        url="https://www.experimental-history.com",
        feed_url="https://www.experimental-history.com/feed",
        tags=["psychology", "science", "humor"],
    ),
    FeedSource(
        name="Dwarkesh Patel",
        url="https://www.dwarkeshpatel.com",
        feed_url="https://www.dwarkeshpatel.com/feed",
        tags=["tech", "interviews", "progress"],
    ),
    FeedSource(
        name="Matt Lakeman",
        url="https://mattlakeman.org",
        feed_url="https://mattlakeman.org/feed/",
        tags=["travel", "culture", "history"],
    ),
    FeedSource(
        name="Roots of Progress",
        url="https://rootsofprogress.org",
        feed_url="https://rootsofprogress.org/feed.xml",
        tags=["progress", "science", "history"],
    ),
    FeedSource(
        name="Cold Takes (Holden Karnofsky)",
        url="https://www.cold-takes.com",
        feed_url="https://www.cold-takes.com/feed/",
        tags=["AI", "philanthropy", "futurism"],
    ),
    FeedSource(
        name="Applied Divinity Studies",
        url="https://applieddivinitystudies.com",
        feed_url="https://applieddivinitystudies.com/feed/",
        tags=["rationality", "culture", "contrarian"],
    ),
]


def get_suggestions(
    prefs: Preferences,
    existing_urls: set[str],
) -> list[FeedSource]:
    """Return suggested blogs, filtered by preferences.

    Excludes blogs the user already follows or has discarded.
    Ranks by tag overlap with liked blogs.
    """
    liked_tags = prefs.liked_tags()
    candidates: list[tuple[FeedSource, int]] = []

    for feed in SUGGESTED_FEEDS:
        key = normalize_url(feed.url)
        if key in existing_urls:
            continue
        if prefs.is_discarded(feed.url):
            continue
        if prefs.is_liked(feed.url):
            continue

        score = sum(liked_tags.get(tag, 0) for tag in feed.tags)
        candidates.append((feed, score))

    candidates.sort(key=lambda x: (-x[1], x[0].name))
    return [feed for feed, _ in candidates]
