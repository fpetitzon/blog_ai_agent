"""Tests for the web UI."""

from unittest.mock import MagicMock, patch

from blog_agent.config import Settings
from blog_agent.models import BlogPost
from blog_agent.preferences import Preferences
from blog_agent.web import create_app


def _make_test_posts():
    return [
        BlogPost(
            title="Test Post 1",
            author="Alice",
            url="https://example.com/p1",
            source_name="Blog A",
        ),
        BlogPost(
            title="Test Post 2",
            author="Bob",
            url="https://example.com/p2",
            source_name="Blog B",
            is_read=True,
        ),
    ]


# Patch storage globally so DB calls don't hit disk in tests
_STORAGE_PATCHES = {
    "blog_agent.web.open_db": MagicMock,
    "blog_agent.web.upsert_posts": MagicMock(return_value=0),
}


class TestWebApp:
    def test_index_returns_html(self):
        app = create_app(Settings(check_firefox_history=False))
        with app.test_client() as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert b"Blog Discovery Agent" in resp.data

    def test_api_posts_returns_json(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)
        # Pre-populate cache to avoid actual feed fetching
        app.config["CACHED_POSTS"] = _make_test_posts()

        with app.test_client() as client:
            resp = client.get("/api/posts")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "posts" in data
            assert "lookback_days" in data
            assert len(data["posts"]) == 2
            assert data["posts"][0]["title"] == "Test Post 1"
            assert data["posts"][1]["is_read"] is True

    def test_api_refresh(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch(
                "blog_agent.web.fetch_all_feeds",
                return_value=_make_test_posts(),
            ),
            patch("blog_agent.web.open_db"),
            patch("blog_agent.web.upsert_posts", return_value=0),
        ):
            with app.test_client() as client:
                resp = client.post("/api/refresh")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["status"] == "ok"
                assert data["count"] == 2

    def test_api_posts_triggers_fetch_when_empty(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch(
                "blog_agent.web.fetch_all_feeds",
                return_value=_make_test_posts(),
            ),
            patch("blog_agent.web.open_db"),
            patch("blog_agent.web.upsert_posts", return_value=0),
        ):
            with app.test_client() as client:
                resp = client.get("/api/posts")
                assert resp.status_code == 200
                data = resp.get_json()
                assert len(data["posts"]) == 2

    def test_api_posts_with_days_param(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch(
                "blog_agent.web.fetch_all_feeds",
                return_value=_make_test_posts(),
            ),
            patch("blog_agent.web.open_db"),
            patch("blog_agent.web.upsert_posts", return_value=0),
        ):
            with app.test_client() as client:
                resp = client.get("/api/posts?days=14")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["lookback_days"] == 14

    def test_api_posts_returns_lookback_days(self):
        settings = Settings(check_firefox_history=False, lookback_days=5)
        app = create_app(settings)
        app.config["CACHED_POSTS"] = _make_test_posts()

        with app.test_client() as client:
            resp = client.get("/api/posts")
            data = resp.get_json()
            assert data["lookback_days"] == 5


class TestSuggestionsAPI:
    def test_api_suggestions_returns_json(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch(
                "blog_agent.web.load_preferences",
                return_value=Preferences(),
            ),
            patch(
                "blog_agent.web._get_or_generate_reasons",
                return_value={},
            ),
        ):
            with app.test_client() as client:
                resp = client.get("/api/suggestions")
                assert resp.status_code == 200
                data = resp.get_json()
                assert "suggestions" in data
                assert "liked" in data
                assert "discarded_count" in data
                assert isinstance(data["suggestions"], list)
                assert len(data["suggestions"]) > 0

    def test_suggestions_include_reason_field(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch(
                "blog_agent.web.load_preferences",
                return_value=Preferences(),
            ),
            patch(
                "blog_agent.web._get_or_generate_reasons",
                return_value={},
            ),
        ):
            with app.test_client() as client:
                resp = client.get("/api/suggestions")
                data = resp.get_json()
                # Every suggestion should have a "reason" field
                for s in data["suggestions"]:
                    assert "reason" in s

    def test_api_like_requires_url(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with app.test_client() as client:
            resp = client.post(
                "/api/suggestions/like",
                json={},
            )
            assert resp.status_code == 400
            assert "url" in resp.get_json()["error"]

    def test_api_like_success(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch("blog_agent.web.load_preferences", return_value=Preferences()),
            patch("blog_agent.web.save_preferences") as mock_save,
        ):
            with app.test_client() as client:
                resp = client.post(
                    "/api/suggestions/like",
                    json={
                        "name": "Test Blog",
                        "url": "https://test.com",
                        "tags": ["tech"],
                    },
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["status"] == "ok"
                assert data["liked_count"] == 1
                mock_save.assert_called_once()

    def test_api_discard_requires_url(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with app.test_client() as client:
            resp = client.post(
                "/api/suggestions/discard",
                json={},
            )
            assert resp.status_code == 400

    def test_api_discard_success(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch("blog_agent.web.load_preferences", return_value=Preferences()),
            patch("blog_agent.web.save_preferences") as mock_save,
        ):
            with app.test_client() as client:
                resp = client.post(
                    "/api/suggestions/discard",
                    json={"url": "https://test.com"},
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["status"] == "ok"
                assert data["discarded_count"] == 1
                mock_save.assert_called_once()

    def test_api_refresh_button(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with (
            patch(
                "blog_agent.web.fetch_all_feeds",
                return_value=_make_test_posts(),
            ),
            patch("blog_agent.web.open_db"),
            patch("blog_agent.web.upsert_posts", return_value=0),
        ):
            with app.test_client() as client:
                resp = client.post("/api/refresh")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["status"] == "ok"

                # After refresh, posts should be cached
                resp2 = client.get("/api/posts")
                data2 = resp2.get_json()
                assert len(data2["posts"]) == 2

    def test_api_like_no_body(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with app.test_client() as client:
            resp = client.post(
                "/api/suggestions/like",
                content_type="application/json",
            )
            assert resp.status_code == 400


class TestDigestAPI:
    def test_api_digest_without_ai(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)
        app.config["CACHED_POSTS"] = _make_test_posts()

        with (
            patch("blog_agent.web.open_db") as mock_open,
            patch("blog_agent.web.get_latest_digest", return_value=None),
            patch("blog_agent.web.generate_digest", return_value=None),
        ):
            mock_conn = MagicMock()
            mock_open.return_value = mock_conn
            with app.test_client() as client:
                resp = client.get("/api/digest")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["digest"] is None
                assert "error" in data

    def test_api_digest_with_cached(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        from datetime import datetime, timezone

        cached = {
            "content": "Cached digest text",
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "lookback_days": 3,
        }

        with (
            patch("blog_agent.web.open_db") as mock_open,
            patch("blog_agent.web.get_latest_digest", return_value=cached),
        ):
            mock_conn = MagicMock()
            mock_open.return_value = mock_conn
            with app.test_client() as client:
                resp = client.get("/api/digest")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["digest"] == "Cached digest text"
                assert data["cached"] is True

    def test_api_digest_generates_new(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)
        app.config["CACHED_POSTS"] = _make_test_posts()

        with (
            patch("blog_agent.web.open_db") as mock_open,
            patch("blog_agent.web.get_latest_digest", return_value=None),
            patch(
                "blog_agent.web.generate_digest",
                return_value="Fresh digest",
            ),
            patch("blog_agent.web.save_digest"),
        ):
            mock_conn = MagicMock()
            mock_open.return_value = mock_conn
            with app.test_client() as client:
                resp = client.get("/api/digest")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["digest"] == "Fresh digest"
                assert data["cached"] is False

    def test_digest_tab_in_html(self):
        app = create_app(Settings(check_firefox_history=False))
        with app.test_client() as client:
            resp = client.get("/")
            assert b"Digest" in resp.data
            assert b"digestTab" in resp.data
            assert b"generateDigestBtn" in resp.data
