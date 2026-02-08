"""Tests for the SQLite storage module."""

from datetime import datetime, timedelta, timezone

from blog_agent.models import BlogPost
from blog_agent.storage import (
    get_latest_digest,
    get_post_count,
    get_posts,
    get_suggestion_reasons,
    open_db,
    save_digest,
    save_suggestion_reasons,
    upsert_posts,
)


def _make_post(**kwargs):
    defaults = {
        "title": "Test Post",
        "author": "Alice",
        "url": "https://example.com/p1",
        "published": datetime.now(tz=timezone.utc),
        "summary": "A test post",
        "source_name": "Test Blog",
    }
    defaults.update(kwargs)
    return BlogPost(**defaults)


class TestOpenDb:
    def test_creates_database(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_creates_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "posts" in table_names
        assert "digests" in table_names
        assert "suggestion_reasons" in table_names
        conn.close()

    def test_creates_parent_dirs(self, tmp_path):
        db_path = tmp_path / "deep" / "nested" / "test.db"
        conn = open_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn1 = open_db(db_path)
        conn1.close()
        conn2 = open_db(db_path)
        conn2.close()


class TestUpsertPosts:
    def test_insert_new_posts(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        posts = [_make_post(), _make_post(url="https://example.com/p2")]
        new_count = upsert_posts(conn, posts)
        assert new_count == 2
        assert get_post_count(conn) == 2
        conn.close()

    def test_update_existing_post(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        post = _make_post(title="Original")
        upsert_posts(conn, [post])

        updated = _make_post(title="Updated")
        new_count = upsert_posts(conn, [updated])
        assert new_count == 0

        rows = conn.execute("SELECT title FROM posts").fetchall()
        assert rows[0]["title"] == "Updated"
        conn.close()

    def test_preserves_is_read_on_update(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        post = _make_post(is_read=True)
        upsert_posts(conn, [post])

        # Update with is_read=False — should preserve True
        updated = _make_post(is_read=False)
        upsert_posts(conn, [updated])

        rows = conn.execute("SELECT is_read FROM posts").fetchall()
        assert bool(rows[0]["is_read"]) is True
        conn.close()

    def test_handles_null_published(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        post = _make_post(published=None)
        upsert_posts(conn, [post])
        assert get_post_count(conn) == 1
        conn.close()

    def test_handles_null_likes_comments(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        post = _make_post(likes=None, comments=None)
        upsert_posts(conn, [post])

        stored = get_posts(conn)
        assert stored[0].likes is None
        assert stored[0].comments is None
        conn.close()


class TestGetPosts:
    def test_returns_all_posts(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        posts = [
            _make_post(url="https://example.com/p1"),
            _make_post(url="https://example.com/p2"),
        ]
        upsert_posts(conn, posts)
        result = get_posts(conn)
        assert len(result) == 2
        conn.close()

    def test_filter_by_lookback_days(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        now = datetime.now(tz=timezone.utc)
        recent = _make_post(
            url="https://example.com/recent",
            published=now - timedelta(hours=12),
        )
        old = _make_post(
            url="https://example.com/old",
            published=now - timedelta(days=10),
        )
        upsert_posts(conn, [recent, old])

        result = get_posts(conn, lookback_days=3)
        assert len(result) == 1
        assert result[0].url == "https://example.com/recent"
        conn.close()

    def test_filter_by_source_name(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        posts = [
            _make_post(url="https://a.com/1", source_name="Blog A"),
            _make_post(url="https://b.com/1", source_name="Blog B"),
        ]
        upsert_posts(conn, posts)

        result = get_posts(conn, source_name="Blog A")
        assert len(result) == 1
        assert result[0].source_name == "Blog A"
        conn.close()

    def test_ordered_by_published_desc(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        now = datetime.now(tz=timezone.utc)
        posts = [
            _make_post(
                url="https://example.com/old",
                published=now - timedelta(days=2),
            ),
            _make_post(
                url="https://example.com/new",
                published=now,
            ),
        ]
        upsert_posts(conn, posts)
        result = get_posts(conn)
        assert result[0].url == "https://example.com/new"
        assert result[1].url == "https://example.com/old"
        conn.close()

    def test_null_published_at_end(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        posts = [
            _make_post(url="https://example.com/no-date", published=None),
            _make_post(
                url="https://example.com/dated",
                published=datetime.now(tz=timezone.utc),
            ),
        ]
        upsert_posts(conn, posts)
        result = get_posts(conn)
        assert result[0].url == "https://example.com/dated"
        assert result[1].url == "https://example.com/no-date"
        conn.close()

    def test_roundtrip_preserves_data(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        now = datetime.now(tz=timezone.utc)
        post = _make_post(
            title="Roundtrip Test",
            author="Bob",
            url="https://example.com/roundtrip",
            published=now,
            summary="Summary text",
            likes=42,
            comments=7,
            source_name="Blog X",
            is_read=True,
        )
        upsert_posts(conn, [post])
        result = get_posts(conn)

        assert len(result) == 1
        p = result[0]
        assert p.title == "Roundtrip Test"
        assert p.author == "Bob"
        assert p.summary == "Summary text"
        assert p.likes == 42
        assert p.comments == 7
        assert p.source_name == "Blog X"
        assert p.is_read is True
        conn.close()


class TestDigestStorage:
    def test_save_and_get_digest(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        save_digest(conn, "Test digest content", lookback_days=5)
        result = get_latest_digest(conn)
        assert result is not None
        assert result["content"] == "Test digest content"
        assert result["lookback_days"] == 5
        conn.close()

    def test_get_latest_digest_empty(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        result = get_latest_digest(conn)
        assert result is None
        conn.close()

    def test_get_latest_returns_newest(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        save_digest(conn, "First digest")
        save_digest(conn, "Second digest")
        result = get_latest_digest(conn)
        assert result["content"] == "Second digest"
        conn.close()


class TestSuggestionReasons:
    def test_save_and_get_reasons(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        reasons = {
            "https://a.com": "Great tech blog",
            "https://b.com": "Interesting perspectives",
        }
        save_suggestion_reasons(conn, reasons)
        result = get_suggestion_reasons(conn)
        assert result == reasons
        conn.close()

    def test_empty_reasons(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        result = get_suggestion_reasons(conn)
        assert result == {}
        conn.close()

    def test_upsert_reason(self, tmp_path):
        conn = open_db(tmp_path / "test.db")
        save_suggestion_reasons(conn, {"https://a.com": "Old reason"})
        save_suggestion_reasons(conn, {"https://a.com": "New reason"})
        result = get_suggestion_reasons(conn)
        assert result["https://a.com"] == "New reason"
        conn.close()
