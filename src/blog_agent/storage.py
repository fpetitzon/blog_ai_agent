"""SQLite persistence for blog posts, digests, and suggestion reasons."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from blog_agent.models import BlogPost

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".config" / "blog-agent" / "posts.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS posts (
    url TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    published TEXT,
    summary TEXT NOT NULL DEFAULT '',
    likes INTEGER,
    comments INTEGER,
    source_name TEXT NOT NULL DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    content TEXT NOT NULL,
    lookback_days INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS suggestion_reasons (
    url TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def open_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (and initialize if needed) the SQLite database."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def upsert_posts(conn: sqlite3.Connection, posts: list[BlogPost]) -> int:
    """Insert or update posts. Returns the number of newly inserted posts."""
    now = datetime.now(tz=timezone.utc).isoformat()
    new_count = 0
    for post in posts:
        published = post.published.isoformat() if post.published else None
        existing = conn.execute(
            "SELECT url, is_read FROM posts WHERE url = ?", (post.url,)
        ).fetchone()
        if existing:
            # Preserve is_read if already marked read
            is_read = existing["is_read"] or int(post.is_read)
            conn.execute(
                """UPDATE posts SET title=?, author=?, published=?, summary=?,
                   likes=?, comments=?, source_name=?, is_read=?, last_seen=?
                   WHERE url=?""",
                (
                    post.title,
                    post.author,
                    published,
                    post.summary,
                    post.likes,
                    post.comments,
                    post.source_name,
                    is_read,
                    now,
                    post.url,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO posts
                   (url, title, author, published, summary,
                    likes, comments, source_name, is_read, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    post.url,
                    post.title,
                    post.author,
                    published,
                    post.summary,
                    post.likes,
                    post.comments,
                    post.source_name,
                    int(post.is_read),
                    now,
                    now,
                ),
            )
            new_count += 1
    conn.commit()
    return new_count


def get_posts(
    conn: sqlite3.Connection,
    lookback_days: int | None = None,
    source_name: str | None = None,
) -> list[BlogPost]:
    """Retrieve posts from the database, newest first."""
    query = "SELECT * FROM posts"
    params: list[str] = []
    conditions: list[str] = []

    if lookback_days is not None:
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
        ).isoformat()
        conditions.append("(published >= ? OR published IS NULL)")
        params.append(cutoff)

    if source_name:
        conditions.append("source_name = ?")
        params.append(source_name)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    # SQLite doesn't support NULLS LAST, so we use a CASE expression
    query += " ORDER BY CASE WHEN published IS NULL THEN 1 ELSE 0 END, published DESC"

    rows = conn.execute(query, params).fetchall()
    posts: list[BlogPost] = []
    for row in rows:
        published = None
        if row["published"]:
            published = datetime.fromisoformat(row["published"])
        posts.append(
            BlogPost(
                title=row["title"],
                author=row["author"],
                url=row["url"],
                published=published,
                summary=row["summary"],
                likes=row["likes"],
                comments=row["comments"],
                source_name=row["source_name"],
                is_read=bool(row["is_read"]),
            )
        )
    return posts


def get_post_count(conn: sqlite3.Connection) -> int:
    """Return total number of stored posts."""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM posts").fetchone()
    return row["cnt"]


# --- Digest storage ---


def save_digest(conn: sqlite3.Connection, content: str, lookback_days: int = 3) -> None:
    """Save a generated digest."""
    now = datetime.now(tz=timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO digests (created_at, content, lookback_days) VALUES (?, ?, ?)",
        (now, content, lookback_days),
    )
    conn.commit()


def get_latest_digest(conn: sqlite3.Connection) -> dict[str, str | int] | None:
    """Get the most recent digest, or None."""
    row = conn.execute(
        "SELECT * FROM digests ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if row:
        return {
            "content": row["content"],
            "created_at": row["created_at"],
            "lookback_days": row["lookback_days"],
        }
    return None


# --- Suggestion reasons storage ---


def save_suggestion_reasons(conn: sqlite3.Connection, reasons: dict[str, str]) -> None:
    """Save generated suggestion reasons (url -> reason)."""
    now = datetime.now(tz=timezone.utc).isoformat()
    for url, reason in reasons.items():
        conn.execute(
            """INSERT OR REPLACE INTO suggestion_reasons (url, reason, created_at)
               VALUES (?, ?, ?)""",
            (url, reason, now),
        )
    conn.commit()


def get_suggestion_reasons(conn: sqlite3.Connection) -> dict[str, str]:
    """Get all cached suggestion reasons as {url: reason}."""
    rows = conn.execute("SELECT url, reason FROM suggestion_reasons").fetchall()
    return {row["url"]: row["reason"] for row in rows}
