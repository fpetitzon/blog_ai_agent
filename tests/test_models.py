"""Tests for data models."""

from datetime import datetime, timedelta, timezone

from blog_agent.models import BlogPost, FeedSource, FeedType


class TestFeedSource:
    def test_get_feed_url_with_explicit_url(self):
        source = FeedSource(
            name="Test",
            url="https://example.com",
            feed_url="https://example.com/rss.xml",
        )
        assert source.get_feed_url() == "https://example.com/rss.xml"

    def test_get_feed_url_fallback(self):
        source = FeedSource(name="Test", url="https://example.com")
        assert source.get_feed_url() == "https://example.com/feed"

    def test_get_feed_url_strips_trailing_slash(self):
        source = FeedSource(name="Test", url="https://example.com/")
        assert source.get_feed_url() == "https://example.com/feed"

    def test_default_feed_type(self):
        source = FeedSource(name="Test", url="https://example.com")
        assert source.feed_type == FeedType.RSS

    def test_tags_default_to_empty(self):
        source = FeedSource(name="Test", url="https://example.com")
        assert source.tags == []

    def test_tags_preserved(self):
        source = FeedSource(name="Test", url="https://example.com", tags=["a", "b"])
        assert source.tags == ["a", "b"]


class TestBlogPost:
    def test_age_days_recent(self):
        now = datetime.now(tz=timezone.utc)
        post = BlogPost(
            title="Test",
            author="Author",
            url="https://example.com/post",
            published=now - timedelta(days=2),
        )
        assert post.age_days() == 2

    def test_age_days_none_when_no_date(self):
        post = BlogPost(
            title="Test",
            author="Author",
            url="https://example.com/post",
        )
        assert post.age_days() is None

    def test_short_summary_short_text(self):
        post = BlogPost(
            title="Test",
            author="Author",
            url="https://example.com/post",
            summary="Short text.",
        )
        assert post.short_summary() == "Short text."

    def test_short_summary_truncation(self):
        long_text = "A" * 200
        post = BlogPost(
            title="Test",
            author="Author",
            url="https://example.com/post",
            summary=long_text,
        )
        result = post.short_summary(max_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_is_read_default_false(self):
        post = BlogPost(
            title="Test",
            author="Author",
            url="https://example.com/post",
        )
        assert post.is_read is False

    def test_likes_optional(self):
        post = BlogPost(
            title="Test",
            author="Author",
            url="https://example.com/post",
        )
        assert post.likes is None

    def test_full_construction(self):
        now = datetime.now(tz=timezone.utc)
        post = BlogPost(
            title="My Post",
            author="Alice",
            url="https://example.com/post",
            published=now,
            summary="A great post",
            likes=42,
            comments=10,
            source_name="Test Blog",
            is_read=True,
        )
        assert post.title == "My Post"
        assert post.author == "Alice"
        assert post.likes == 42
        assert post.comments == 10
        assert post.source_name == "Test Blog"
        assert post.is_read is True
