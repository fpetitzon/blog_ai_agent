"""Tests for configuration."""

import json
from unittest.mock import patch

from blog_agent.config import Settings
from blog_agent.models import DEFAULT_FEEDS, FeedSource
from blog_agent.preferences import Preferences


class TestSettings:
    def test_default_lookback_days(self):
        settings = Settings()
        assert settings.lookback_days == 3

    def test_default_check_firefox_history(self):
        settings = Settings()
        assert settings.check_firefox_history is True

    def test_default_feeds(self):
        settings = Settings()
        feeds = settings.get_feeds()
        assert len(feeds) == len(DEFAULT_FEEDS)
        names = {f.name for f in feeds}
        assert "Marginal Revolution" in names
        assert "Astral Codex Ten" in names

    def test_custom_feeds_file(self, tmp_path):
        feeds_data = [
            {"name": "Custom Blog", "url": "https://custom.example.com"},
        ]
        feeds_file = tmp_path / "feeds.json"
        feeds_file.write_text(json.dumps(feeds_data))

        settings = Settings(feeds_file=str(feeds_file))
        feeds = settings.get_feeds()
        assert len(feeds) == 1
        assert feeds[0].name == "Custom Blog"

    def test_missing_feeds_file_returns_defaults(self):
        settings = Settings(feeds_file="/nonexistent/path.json")
        feeds = settings.get_feeds()
        assert len(feeds) == len(DEFAULT_FEEDS)

    def test_request_timeout_default(self):
        settings = Settings()
        assert settings.request_timeout == 15

    def test_max_concurrent_default(self):
        settings = Settings()
        assert settings.max_concurrent == 5


class TestDiscoveryLoop:
    def test_liked_blogs_merged_into_feeds(self):
        liked_blog = FeedSource(
            name="Liked Blog",
            url="https://liked.example.com",
            tags=["tech"],
        )
        prefs = Preferences(liked=[liked_blog])

        with patch(
            "blog_agent.preferences.load_preferences", return_value=prefs
        ):
            settings = Settings()
            feeds = settings.get_feeds()

        urls = {f.url for f in feeds}
        assert "https://liked.example.com" in urls
        assert len(feeds) == len(DEFAULT_FEEDS) + 1

    def test_liked_duplicates_not_added(self):
        """A liked blog whose URL matches a default feed should not duplicate."""
        first_default = DEFAULT_FEEDS[0]
        liked_blog = FeedSource(
            name=first_default.name,
            url=first_default.url,
            tags=["duplicate"],
        )
        prefs = Preferences(liked=[liked_blog])

        with patch(
            "blog_agent.preferences.load_preferences", return_value=prefs
        ):
            settings = Settings()
            feeds = settings.get_feeds()

        assert len(feeds) == len(DEFAULT_FEEDS)

    def test_empty_preferences_returns_defaults(self):
        with patch(
            "blog_agent.preferences.load_preferences",
            return_value=Preferences(),
        ):
            settings = Settings()
            feeds = settings.get_feeds()
        assert len(feeds) == len(DEFAULT_FEEDS)
