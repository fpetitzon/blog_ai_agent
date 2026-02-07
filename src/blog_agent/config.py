"""Configuration management for the blog agent."""

from __future__ import annotations

import json
import platform
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

from blog_agent.models import DEFAULT_FEEDS, FeedSource


def _default_firefox_profile_dir() -> str:
    """Return the default Firefox profile directory for the current OS."""
    system = platform.system()
    home = Path.home()
    if system == "Linux":
        return str(home / ".mozilla" / "firefox")
    elif system == "Darwin":
        return str(home / "Library" / "Application Support" / "Firefox" / "Profiles")
    elif system == "Windows":
        return str(home / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles")
    return str(home / ".mozilla" / "firefox")


class Settings(BaseSettings):
    """Application settings, configurable via environment variables."""

    # How many days back to look for new posts
    lookback_days: int = Field(default=3, ge=1, le=90)

    # Firefox profile directory (auto-detected)
    firefox_profile_dir: str = Field(default_factory=_default_firefox_profile_dir)

    # Whether to check Firefox history for read status
    check_firefox_history: bool = True

    # Path to a JSON file with custom feed sources
    feeds_file: str | None = None

    # Request timeout in seconds
    request_timeout: int = Field(default=15, ge=1, le=120)

    # Maximum concurrent feed fetches
    max_concurrent: int = Field(default=5, ge=1, le=20)

    model_config = {"env_prefix": "BLOG_AGENT_"}

    def get_feeds(self) -> list[FeedSource]:
        """Load feed sources from file or return defaults."""
        if self.feeds_file:
            path = Path(self.feeds_file)
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                return [FeedSource(**item) for item in data]
        return list(DEFAULT_FEEDS)
