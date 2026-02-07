"""Tests for blog discovery."""

from unittest.mock import patch

import httpx

from blog_agent.discovery import (
    _is_valid_substack_url,
    _looks_like_blog,
    discover_blogroll_links,
    discover_related_feeds,
    discover_substack_recommendations,
)
from blog_agent.models import FeedSource


class TestIsValidSubstackUrl:
    def test_valid_substack(self):
        assert _is_valid_substack_url("https://test.substack.com") is True

    def test_substack_post_url(self):
        assert _is_valid_substack_url("https://test.substack.com/p/my-post") is False

    def test_non_http(self):
        assert _is_valid_substack_url("ftp://test.substack.com") is False

    def test_empty(self):
        assert _is_valid_substack_url("") is False

    def test_none(self):
        assert _is_valid_substack_url(None) is False


class TestLooksLikeBlog:
    def test_blog_url(self):
        assert _looks_like_blog("https://myblog.com/") is True

    def test_twitter(self):
        assert _looks_like_blog("https://twitter.com/user") is False

    def test_deep_path(self):
        assert _looks_like_blog("https://example.com/a/b/c/d") is False

    def test_substack(self):
        assert _looks_like_blog("https://blog.substack.com") is True

    def test_github(self):
        assert _looks_like_blog("https://github.com/repo") is False


class TestDiscoverSubstackRecommendations:
    def test_non_substack_returns_empty(self):
        source = FeedSource(name="WordPress", url="https://myblog.wordpress.com")
        mock_response = httpx.Response(
            status_code=200,
            text="<html><body>Just a blog</body></html>",
            request=httpx.Request("GET", "https://myblog.wordpress.com"),
        )
        with patch("blog_agent.discovery.httpx.get", return_value=mock_response):
            result = discover_substack_recommendations(source)
        assert result == []

    def test_substack_with_recommendations(self):
        source = FeedSource(
            name="Test Substack",
            url="https://test.substack.com",
        )
        html = """
        <html><body>
            <a href="https://rec1.substack.com">Recommended Blog 1</a>
            <a href="https://rec2.substack.com">Recommended Blog 2</a>
            <a href="https://rec1.substack.com">Duplicate</a>
        </body></html>
        """
        mock_response = httpx.Response(
            status_code=200,
            text=html,
            request=httpx.Request("GET", "https://test.substack.com/recommendations"),
        )
        with patch("blog_agent.discovery.httpx.get", return_value=mock_response):
            result = discover_substack_recommendations(source)

        # Should deduplicate
        assert len(result) == 2
        names = {r.name for r in result}
        assert "Recommended Blog 1" in names
        assert "Recommended Blog 2" in names

    def test_handles_network_error(self):
        source = FeedSource(name="Test", url="https://test.substack.com")
        with patch(
            "blog_agent.discovery.httpx.get",
            side_effect=httpx.ConnectError("fail"),
        ):
            result = discover_substack_recommendations(source)
        assert result == []


class TestDiscoverBlogrollLinks:
    def test_finds_blogroll_links(self):
        source = FeedSource(name="Blog", url="https://example.com")
        html = """
        <html><body>
            <article>
                <a href="https://coolblog.com">Cool Blog</a>
                <a href="https://twitter.com/user">Twitter</a>
                <a href="https://anotherblog.org/">Another Blog</a>
            </article>
        </body></html>
        """
        mock_response_404 = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://example.com/blogroll"),
        )
        mock_response_ok = httpx.Response(
            status_code=200,
            text=html,
            request=httpx.Request("GET", "https://example.com/links"),
        )

        def mock_get(url, **kwargs):
            if "/links" in url:
                return mock_response_ok
            return mock_response_404

        with patch("blog_agent.discovery.httpx.get", side_effect=mock_get):
            result = discover_blogroll_links(source)

        # Should find coolblog and anotherblog, but not twitter
        urls = {r.url for r in result}
        assert "https://coolblog.com" in urls
        assert "https://anotherblog.org" in urls


class TestDiscoverRelatedFeeds:
    def test_deduplicates_against_existing(self):
        sources = [
            FeedSource(name="Existing", url="https://existing.substack.com"),
        ]
        discovered = FeedSource(
            name="Existing Dup",
            url="https://existing.substack.com",
            tags=["discovered"],
        )
        new_feed = FeedSource(
            name="New Blog",
            url="https://new.substack.com",
            tags=["discovered"],
        )

        with (
            patch(
                "blog_agent.discovery.discover_substack_recommendations",
                return_value=[discovered, new_feed],
            ),
            patch(
                "blog_agent.discovery.discover_blogroll_links",
                return_value=[],
            ),
        ):
            result = discover_related_feeds(sources)

        assert len(result) == 1
        assert result[0].url == "https://new.substack.com"
