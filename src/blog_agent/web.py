"""Web UI for the blog discovery agent."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template

from blog_agent.config import Settings
from blog_agent.feeds import fetch_all_feeds
from blog_agent.firefox_history import get_visited_urls, mark_read_posts

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> Flask:
    """Create and configure the Flask application."""
    template_dir = Path(__file__).parent / "templates"
    app = Flask(__name__, template_folder=str(template_dir))

    if settings is None:
        settings = Settings()

    # Store settings on app for access in routes
    app.config["BLOG_SETTINGS"] = settings

    # Cache for fetched posts (refreshed via /api/refresh)
    app.config["CACHED_POSTS"] = None

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/posts")
    def api_posts():
        """Return all posts as JSON, fetching if not cached."""
        if app.config["CACHED_POSTS"] is None:
            _refresh_posts(app)
        posts = app.config["CACHED_POSTS"] or []
        return jsonify([p.model_dump(mode="json") for p in posts])

    @app.route("/api/refresh", methods=["POST"])
    def api_refresh():
        """Force a refresh of all feeds."""
        _refresh_posts(app)
        count = len(app.config["CACHED_POSTS"] or [])
        return jsonify({"status": "ok", "count": count})

    return app


def _refresh_posts(app: Flask) -> None:
    """Fetch all feeds and update the cache."""
    settings: Settings = app.config["BLOG_SETTINGS"]
    sources = settings.get_feeds()

    posts = fetch_all_feeds(
        sources,
        timeout=settings.request_timeout,
        lookback_days=settings.lookback_days,
    )

    if settings.check_firefox_history and posts:
        visited = get_visited_urls(
            settings.firefox_profile_dir,
            lookback_days=max(settings.lookback_days, 30),
        )
        if visited:
            mark_read_posts(posts, visited)

    app.config["CACHED_POSTS"] = posts
    logger.info("Refreshed %d posts", len(posts))
