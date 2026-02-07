"""Web UI for the blog discovery agent."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from blog_agent.config import Settings
from blog_agent.feeds import fetch_all_feeds
from blog_agent.firefox_history import get_visited_urls, mark_read_posts
from blog_agent.models import FeedSource, normalize_url
from blog_agent.preferences import (
    get_suggestions,
    load_preferences,
    save_preferences,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> Flask:
    """Create and configure the Flask application."""
    template_dir = Path(__file__).parent / "templates"
    app = Flask(__name__, template_folder=str(template_dir))

    if settings is None:
        settings = Settings()

    app.config["BLOG_SETTINGS"] = settings
    app.config["CACHED_POSTS"] = None
    app.config["CACHED_LOOKBACK"] = settings.lookback_days

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/posts")
    def api_posts():
        """Return posts as JSON. Accepts ?days=N."""
        days = request.args.get("days", type=int)
        if days and days != app.config["CACHED_LOOKBACK"]:
            app.config["CACHED_LOOKBACK"] = days
            _refresh_posts(app, lookback_days=days)
        elif app.config["CACHED_POSTS"] is None:
            _refresh_posts(app)

        posts = app.config["CACHED_POSTS"] or []
        return jsonify(
            {
                "posts": [p.model_dump(mode="json") for p in posts],
                "lookback_days": app.config["CACHED_LOOKBACK"],
            }
        )

    @app.route("/api/refresh", methods=["POST"])
    def api_refresh():
        """Force a refresh of all feeds."""
        days = request.args.get("days", type=int)
        if days:
            app.config["CACHED_LOOKBACK"] = days
        _refresh_posts(app, lookback_days=app.config["CACHED_LOOKBACK"])
        count = len(app.config["CACHED_POSTS"] or [])
        return jsonify({"status": "ok", "count": count})

    @app.route("/api/suggestions")
    def api_suggestions():
        """Return suggested blogs based on preferences."""
        prefs = load_preferences()
        existing = {normalize_url(s.url) for s in settings.get_feeds()}
        suggestions = get_suggestions(prefs, existing)
        return jsonify(
            {
                "suggestions": [s.model_dump(mode="json") for s in suggestions],
                "liked": [s.model_dump(mode="json") for s in prefs.liked],
                "discarded_count": len(prefs.discarded_urls),
            }
        )

    @app.route("/api/suggestions/like", methods=["POST"])
    def api_like():
        """Like a suggested blog (add to liked list)."""
        data = request.get_json()
        if not data or "url" not in data:
            return jsonify({"error": "url required"}), 400

        source = FeedSource(
            name=data.get("name", "Unknown"),
            url=data["url"],
            feed_url=data.get("feed_url"),
            tags=data.get("tags", []),
        )

        prefs = load_preferences()
        prefs.like(source)
        save_preferences(prefs)

        return jsonify({"status": "ok", "liked_count": len(prefs.liked)})

    @app.route("/api/suggestions/discard", methods=["POST"])
    def api_discard():
        """Discard a suggested blog."""
        data = request.get_json()
        if not data or "url" not in data:
            return jsonify({"error": "url required"}), 400

        prefs = load_preferences()
        prefs.discard(data["url"])
        save_preferences(prefs)

        return jsonify(
            {
                "status": "ok",
                "discarded_count": len(prefs.discarded_urls),
            }
        )

    return app


def _refresh_posts(app: Flask, lookback_days: int | None = None) -> None:
    """Fetch all feeds and update the cache."""
    settings: Settings = app.config["BLOG_SETTINGS"]
    sources = settings.get_feeds()
    days = lookback_days or settings.lookback_days

    posts = fetch_all_feeds(
        sources,
        timeout=settings.request_timeout,
        lookback_days=days,
    )

    if settings.check_firefox_history and posts:
        visited = get_visited_urls(
            settings.firefox_profile_dir,
            lookback_days=max(days, 30),
        )
        if visited:
            mark_read_posts(posts, visited)

    app.config["CACHED_POSTS"] = posts
    app.config["CACHED_LOOKBACK"] = days
    logger.info("Refreshed %d posts (lookback=%d days)", len(posts), days)
