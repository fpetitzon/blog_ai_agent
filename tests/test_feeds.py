"""Tests for RSS feed fetching and parsing."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx

from blog_agent.feeds import (
    _extract_likes,
    _extract_summary,
    _parse_date,
    fetch_all_feeds,
    fetch_feed,
)
from blog_agent.models import FeedSource

# Sample RSS feed XML for testing
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <link>https://example.com</link>
    <description>A test blog</description>
    <item>
      <title>Recent Post</title>
      <link>https://example.com/recent-post</link>
      <author>Alice</author>
      <pubDate>{recent_date}</pubDate>
      <description>This is a recent post about testing.</description>
    </item>
    <item>
      <title>Old Post</title>
      <link>https://example.com/old-post</link>
      <author>Bob</author>
      <pubDate>{old_date}</pubDate>
      <description>This is an old post.</description>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Blog</title>
  <link href="https://example.com"/>
  <entry>
    <title>Atom Post</title>
    <link href="https://example.com/atom-post"/>
    <author><name>Charlie</name></author>
    <updated>{recent_date}</updated>
    <summary>An atom feed post.</summary>
  </entry>
</feed>
"""


def _make_rss(recent_days_ago: int = 1, old_days_ago: int = 10) -> str:
    """Generate RSS XML with dates relative to now."""
    now = datetime.now(tz=timezone.utc)
    recent = now - timedelta(days=recent_days_ago)
    old = now - timedelta(days=old_days_ago)
    return SAMPLE_RSS.format(
        recent_date=recent.strftime("%a, %d %b %Y %H:%M:%S +0000"),
        old_date=old.strftime("%a, %d %b %Y %H:%M:%S +0000"),
    )


def _make_atom(recent_days_ago: int = 1) -> str:
    now = datetime.now(tz=timezone.utc)
    recent = now - timedelta(days=recent_days_ago)
    return SAMPLE_ATOM.format(
        recent_date=recent.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    )


class TestParseDate:
    def test_parse_rfc2822(self):
        entry = {"published": "Mon, 01 Jan 2024 12:00:00 +0000"}
        result = _parse_date(entry)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1

    def test_parse_iso8601(self):
        entry = {"published": "2024-06-15T10:30:00Z"}
        result = _parse_date(entry)
        assert result is not None
        assert result.year == 2024
        assert result.month == 6

    def test_parse_none_when_missing(self):
        entry = {}
        result = _parse_date(entry)
        assert result is None

    def test_parse_struct_time(self):
        import time

        entry = {"published_parsed": time.strptime("2024-03-15", "%Y-%m-%d")}
        result = _parse_date(entry)
        assert result is not None
        assert result.year == 2024


class TestExtractSummary:
    def test_plain_text(self):
        entry = {"summary": "Hello world"}
        assert _extract_summary(entry) == "Hello world"

    def test_html_stripping(self):
        entry = {"summary": "<p>Hello <b>world</b></p>"}
        assert _extract_summary(entry) == "Hello world"

    def test_empty_summary_fallback_to_content(self):
        entry = {
            "summary": "",
            "content": [{"value": "From content field"}],
        }
        assert _extract_summary(entry) == "From content field"

    def test_empty_entry(self):
        entry = {}
        assert _extract_summary(entry) == ""


class TestExtractLikes:
    def test_slash_comments(self):
        entry = {"slash_comments": "42"}
        assert _extract_likes(entry) == 42

    def test_none_when_missing(self):
        entry = {}
        assert _extract_likes(entry) is None

    def test_invalid_value(self):
        entry = {"slash_comments": "not-a-number"}
        assert _extract_likes(entry) is None


class TestFetchFeed:
    def test_fetch_rss_feed(self):
        source = FeedSource(
            name="Test Blog",
            url="https://example.com",
            feed_url="https://example.com/feed",
        )
        rss_content = _make_rss(recent_days_ago=1, old_days_ago=10)

        mock_response = httpx.Response(
            status_code=200,
            text=rss_content,
            request=httpx.Request("GET", "https://example.com/feed"),
        )

        with patch("blog_agent.feeds.httpx.get", return_value=mock_response):
            posts = fetch_feed(source, lookback_days=3)

        assert len(posts) == 1
        assert posts[0].title == "Recent Post"
        assert posts[0].url == "https://example.com/recent-post"

    def test_fetch_atom_feed(self):
        source = FeedSource(
            name="Atom Blog",
            url="https://example.com",
            feed_url="https://example.com/atom.xml",
        )
        atom_content = _make_atom(recent_days_ago=1)

        mock_response = httpx.Response(
            status_code=200,
            text=atom_content,
            request=httpx.Request("GET", "https://example.com/atom.xml"),
        )

        with patch("blog_agent.feeds.httpx.get", return_value=mock_response):
            posts = fetch_feed(source, lookback_days=3)

        assert len(posts) == 1
        assert posts[0].title == "Atom Post"

    def test_fetch_handles_http_error(self):
        source = FeedSource(name="Bad", url="https://example.com")

        with patch(
            "blog_agent.feeds.httpx.get",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            posts = fetch_feed(source)

        assert posts == []

    def test_fetch_handles_404(self):
        source = FeedSource(name="Missing", url="https://example.com")

        mock_response = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://example.com/feed"),
        )

        with patch("blog_agent.feeds.httpx.get", return_value=mock_response):
            posts = fetch_feed(source)

        assert posts == []


class TestFetchAllFeeds:
    def test_combines_and_sorts(self):
        sources = [
            FeedSource(name="A", url="https://a.com", feed_url="https://a.com/feed"),
            FeedSource(name="B", url="https://b.com", feed_url="https://b.com/feed"),
        ]

        now = datetime.now(tz=timezone.utc)
        rss_a = SAMPLE_RSS.format(
            recent_date=(now - timedelta(hours=2)).strftime(
                "%a, %d %b %Y %H:%M:%S +0000"
            ),
            old_date=(now - timedelta(days=10)).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        )
        rss_b = SAMPLE_RSS.format(
            recent_date=(now - timedelta(hours=1)).strftime(
                "%a, %d %b %Y %H:%M:%S +0000"
            ),
            old_date=(now - timedelta(days=10)).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        )

        def mock_get(url, **kwargs):
            text = rss_a if "a.com" in url else rss_b
            return httpx.Response(
                status_code=200,
                text=text,
                request=httpx.Request("GET", url),
            )

        with patch("blog_agent.feeds.httpx.get", side_effect=mock_get):
            posts = fetch_all_feeds(sources, lookback_days=3)

        # Should have 2 recent posts (old ones filtered out), sorted newest first
        assert len(posts) == 2
        # The one from B (1h ago) should come before A (2h ago)
        assert posts[0].published > posts[1].published
