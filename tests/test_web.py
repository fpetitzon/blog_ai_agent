"""Tests for the web UI."""

from unittest.mock import patch

from blog_agent.config import Settings
from blog_agent.models import BlogPost
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
            assert len(data) == 2
            assert data[0]["title"] == "Test Post 1"
            assert data[1]["is_read"] is True

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
                assert len(data) == 2
