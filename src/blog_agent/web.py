"""Web UI for the blog discovery agent."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from blog_agent.config import Settings
from blog_agent.digest import generate_digest, generate_suggestion_reasons
from blog_agent.feeds import fetch_all_feeds
from blog_agent.firefox_history import get_visited_urls, mark_read_posts
from blog_agent.models import FeedSource, normalize_url
from blog_agent.preferences import (
    get_suggestions,
    load_preferences,
    save_preferences,
)
from blog_agent.storage import (
    get_latest_digest,
    get_suggestion_reasons,
    open_db,
    save_digest,
    save_suggestion_reasons,
    upsert_posts,
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
        """Return suggested blogs with optional AI-generated reasons."""
        prefs = load_preferences()
        existing = {normalize_url(s.url) for s in settings.get_feeds()}
        suggestions = get_suggestions(prefs, existing)

        # Load cached reasons from DB (or generate if missing)
        reasons = _get_or_generate_reasons(
            suggestions, prefs.liked, settings.get_feeds()
        )

        suggestion_data = []
        for s in suggestions:
            d = s.model_dump(mode="json")
            d["reason"] = reasons.get(s.url, "")
            suggestion_data.append(d)

        return jsonify(
            {
                "suggestions": suggestion_data,
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

    @app.route("/api/digest")
    def api_digest():
        """Return an AI-generated digest. Accepts ?force=1 to regenerate."""
        force = request.args.get("force", type=int, default=0)
        conn = open_db()
        try:
            cached = get_latest_digest(conn)
            # Use cached digest if less than 12 hours old and not forced
            if cached and not force:
                created = datetime.fromisoformat(str(cached["created_at"]))
                age = datetime.now(tz=timezone.utc) - created
                if age < timedelta(hours=12):
                    return jsonify({"digest": cached["content"], "cached": True})

            # Generate a new digest from recent posts
            posts = app.config["CACHED_POSTS"]
            if posts is None:
                _refresh_posts(app)
                posts = app.config["CACHED_POSTS"] or []

            days = app.config["CACHED_LOOKBACK"]
            content = generate_digest(posts, lookback_days=days)
            if content:
                save_digest(conn, content, lookback_days=days)
                return jsonify({"digest": content, "cached": False})
            return jsonify({"digest": None, "error": "AI unavailable"})
        finally:
            conn.close()

    return app


def _refresh_posts(app: Flask, lookback_days: int | None = None) -> None:
    """Fetch all feeds, persist to DB, and update the cache."""
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

    # Persist to SQLite
    try:
        conn = open_db()
        new_count = upsert_posts(conn, posts)
        conn.close()
        logger.info("Persisted %d new posts to database", new_count)
    except Exception as exc:
        logger.warning("Could not persist posts: %s", exc)

    app.config["CACHED_POSTS"] = posts
    app.config["CACHED_LOOKBACK"] = days
    logger.info("Refreshed %d posts (lookback=%d days)", len(posts), days)


def _get_or_generate_reasons(
    suggestions: list[FeedSource],
    liked: list[FeedSource],
    existing_feeds: list[FeedSource],
) -> dict[str, str]:
    """Load cached suggestion reasons or generate new ones via AI."""
    try:
        conn = open_db()
    except Exception:
        return {}

    try:
        cached = get_suggestion_reasons(conn)
        # Check if we have reasons for all current suggestions
        missing = [s for s in suggestions if s.url not in cached]
        if not missing:
            return cached

        # Generate reasons for missing suggestions
        new_reasons = generate_suggestion_reasons(missing, liked, existing_feeds)
        if new_reasons:
            save_suggestion_reasons(conn, new_reasons)
            cached.update(new_reasons)
        return cached
    finally:
        conn.close()
