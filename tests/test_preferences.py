"""Tests for the preferences module."""

from blog_agent.models import FeedSource
from blog_agent.preferences import (
    SUGGESTED_FEEDS,
    Preferences,
    get_suggestions,
    load_preferences,
    save_preferences,
)


class TestPreferences:
    def test_empty_preferences(self):
        prefs = Preferences()
        assert prefs.liked == []
        assert prefs.discarded_urls == []

    def test_is_discarded_normalizes_url(self):
        prefs = Preferences(discarded_urls=["https://example.com/"])
        assert prefs.is_discarded("https://example.com")
        assert prefs.is_discarded("https://EXAMPLE.COM/")
        assert not prefs.is_discarded("https://other.com")

    def test_is_liked_normalizes_url(self):
        source = FeedSource(name="Test", url="https://example.com/")
        prefs = Preferences(liked=[source])
        assert prefs.is_liked("https://example.com")
        assert prefs.is_liked("https://EXAMPLE.COM/")
        assert not prefs.is_liked("https://other.com")

    def test_like_adds_source(self):
        prefs = Preferences()
        source = FeedSource(name="Test", url="https://example.com")
        prefs.like(source)
        assert len(prefs.liked) == 1
        assert prefs.is_liked("https://example.com")

    def test_like_removes_from_discarded(self):
        prefs = Preferences(discarded_urls=["https://example.com"])
        source = FeedSource(name="Test", url="https://example.com")
        prefs.like(source)
        assert len(prefs.liked) == 1
        assert not prefs.is_discarded("https://example.com")

    def test_like_no_duplicates(self):
        prefs = Preferences()
        source = FeedSource(name="Test", url="https://example.com")
        prefs.like(source)
        prefs.like(source)
        assert len(prefs.liked) == 1

    def test_discard_adds_url(self):
        prefs = Preferences()
        prefs.discard("https://example.com")
        assert prefs.is_discarded("https://example.com")

    def test_discard_removes_from_liked(self):
        source = FeedSource(name="Test", url="https://example.com")
        prefs = Preferences(liked=[source])
        prefs.discard("https://example.com")
        assert len(prefs.liked) == 0
        assert prefs.is_discarded("https://example.com")

    def test_discard_no_duplicates(self):
        prefs = Preferences()
        prefs.discard("https://example.com")
        prefs.discard("https://example.com")
        assert len(prefs.discarded_urls) == 1

    def test_liked_tags_empty(self):
        prefs = Preferences()
        assert prefs.liked_tags() == {}

    def test_liked_tags_counts(self):
        prefs = Preferences(
            liked=[
                FeedSource(name="A", url="https://a.com", tags=["tech", "ai"]),
                FeedSource(name="B", url="https://b.com", tags=["tech", "science"]),
            ]
        )
        tags = prefs.liked_tags()
        assert tags["tech"] == 2
        assert tags["ai"] == 1
        assert tags["science"] == 1


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "prefs.json"
        prefs = Preferences()
        prefs.like(FeedSource(name="Test", url="https://example.com", tags=["tech"]))
        prefs.discard("https://other.com")

        save_preferences(prefs, path)
        loaded = load_preferences(path)

        assert len(loaded.liked) == 1
        assert loaded.liked[0].name == "Test"
        assert loaded.is_discarded("https://other.com")

    def test_load_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        prefs = load_preferences(path)
        assert prefs.liked == []
        assert prefs.discarded_urls == []

    def test_load_corrupt_file(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json {{{")
        prefs = load_preferences(path)
        assert prefs.liked == []

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "prefs.json"
        prefs = Preferences()
        save_preferences(prefs, path)
        assert path.exists()

    def test_roundtrip_preserves_data(self, tmp_path):
        path = tmp_path / "prefs.json"
        original = Preferences(
            liked=[
                FeedSource(
                    name="Blog A",
                    url="https://a.com",
                    feed_url="https://a.com/feed",
                    tags=["tech", "ai"],
                ),
            ],
            discarded_urls=["https://discarded.com", "https://nope.com"],
        )
        save_preferences(original, path)
        loaded = load_preferences(path)

        assert len(loaded.liked) == 1
        assert loaded.liked[0].feed_url == "https://a.com/feed"
        assert loaded.liked[0].tags == ["tech", "ai"]
        assert len(loaded.discarded_urls) == 2


class TestGetSuggestions:
    def test_returns_suggestions(self):
        prefs = Preferences()
        suggestions = get_suggestions(prefs, set())
        assert len(suggestions) > 0

    def test_excludes_existing_urls(self):
        prefs = Preferences()
        existing = {SUGGESTED_FEEDS[0].url.rstrip("/").lower()}
        suggestions = get_suggestions(prefs, existing)
        urls = {s.url for s in suggestions}
        assert SUGGESTED_FEEDS[0].url not in urls

    def test_excludes_discarded(self):
        prefs = Preferences()
        prefs.discard(SUGGESTED_FEEDS[0].url)
        suggestions = get_suggestions(prefs, set())
        urls = {s.url for s in suggestions}
        assert SUGGESTED_FEEDS[0].url not in urls

    def test_excludes_liked(self):
        prefs = Preferences()
        prefs.like(SUGGESTED_FEEDS[0])
        suggestions = get_suggestions(prefs, set())
        urls = {s.url for s in suggestions}
        assert SUGGESTED_FEEDS[0].url not in urls

    def test_ranks_by_tag_overlap(self):
        # Like a blog with "tech" tag to boost other tech blogs
        prefs = Preferences()
        prefs.like(
            FeedSource(name="Tech Blog", url="https://tech.example.com", tags=["tech"])
        )
        suggestions = get_suggestions(prefs, set())

        # Find tech-tagged suggestions — they should be near the top
        tech_indices = [i for i, s in enumerate(suggestions) if "tech" in s.tags]
        non_tech_indices = [
            i for i, s in enumerate(suggestions) if "tech" not in s.tags
        ]
        if tech_indices and non_tech_indices:
            # At least one tech blog should rank above some non-tech blogs
            assert min(tech_indices) < max(non_tech_indices)

    def test_suggested_feeds_not_empty(self):
        assert len(SUGGESTED_FEEDS) > 0
        for feed in SUGGESTED_FEEDS:
            assert feed.name
            assert feed.url
            assert len(feed.tags) > 0
