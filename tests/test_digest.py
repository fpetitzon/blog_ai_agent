"""Tests for the AI digest module."""

from unittest.mock import MagicMock, patch

from blog_agent.digest import generate_digest, generate_suggestion_reasons
from blog_agent.models import BlogPost, FeedSource


def _make_posts(n=3):
    from datetime import datetime, timezone

    return [
        BlogPost(
            title=f"Post {i}",
            author=f"Author {i}",
            url=f"https://example.com/p{i}",
            published=datetime.now(tz=timezone.utc),
            summary=f"Summary of post {i}",
            source_name=f"Blog {i}",
            comments=i * 10,
        )
        for i in range(1, n + 1)
    ]


class TestGenerateDigest:
    def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = generate_digest(_make_posts())
        assert result is None

    def test_returns_none_for_empty_posts(self):
        result = generate_digest([])
        assert result is None

    @patch("blog_agent.digest._get_client")
    def test_returns_digest_text(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Here is your digest.")]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generate_digest(_make_posts(), lookback_days=3)
        assert result == "Here is your digest."
        mock_client.messages.create.assert_called_once()

    @patch("blog_agent.digest._get_client")
    def test_handles_api_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API down")
        mock_get_client.return_value = mock_client

        result = generate_digest(_make_posts())
        assert result is None

    @patch("blog_agent.digest._get_client")
    def test_returns_none_when_client_unavailable(self, mock_get_client):
        mock_get_client.return_value = None
        result = generate_digest(_make_posts())
        assert result is None


class TestGenerateSuggestionReasons:
    def test_returns_empty_without_client(self):
        with patch("blog_agent.digest._get_client", return_value=None):
            result = generate_suggestion_reasons(
                [FeedSource(name="Test", url="https://test.com", tags=["tech"])],
                [],
                [],
            )
        assert result == {}

    def test_returns_empty_for_no_suggestions(self):
        result = generate_suggestion_reasons([], [], [])
        assert result == {}

    @patch("blog_agent.digest._get_client")
    def test_parses_reasons(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Test Blog: Great for tech enthusiasts")
        ]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        suggestions = [
            FeedSource(name="Test Blog", url="https://test.com", tags=["tech"])
        ]
        result = generate_suggestion_reasons(suggestions, [], [])
        assert "https://test.com" in result
        assert "tech enthusiasts" in result["https://test.com"]

    @patch("blog_agent.digest._get_client")
    def test_handles_api_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API error")
        mock_get_client.return_value = mock_client

        suggestions = [FeedSource(name="Test", url="https://test.com", tags=["tech"])]
        result = generate_suggestion_reasons(suggestions, [], [])
        assert result == {}
