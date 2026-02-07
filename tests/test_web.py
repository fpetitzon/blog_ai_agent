"""Tests for the web UI."""

from unittest.mock import patch

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

        with patch(
            "blog_agent.web.fetch_all_feeds",
            return_value=_make_test_posts(),
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

        with patch(
            "blog_agent.web.fetch_all_feeds",
            return_value=_make_test_posts(),
        ):
            with app.test_client() as client:
                resp = client.get("/api/posts")
                assert resp.status_code == 200
                data = resp.get_json()
                assert len(data["posts"]) == 2

    def test_api_posts_with_days_param(self):
        settings = Settings(check_firefox_history=False)
        app = create_app(settings)

        with patch(
            "blog_agent.web.fetch_all_feeds",
            return_value=_make_test_posts(),
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

        with patch(
            "blog_agent.web.load_preferences",
            return_value=Preferences(),
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

        with patch(
            "blog_agent.web.fetch_all_feeds",
            return_value=_make_test_posts(),
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
