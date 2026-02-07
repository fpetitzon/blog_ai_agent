"""Tests for Firefox history reading."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from blog_agent.firefox_history import (
    _query_history,
    find_default_profile,
    get_visited_urls,
    mark_read_posts,
    normalize_url,
)
from blog_agent.models import BlogPost


class TestNormalizeUrl:
    def test_basic_url(self):
        assert normalize_url("https://example.com/post") == ("https://example.com/post")

    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.com/post/") == (
            "https://example.com/post"
        )

    def test_strips_query_and_fragment(self):
        assert normalize_url("https://example.com/post?ref=twitter#comments") == (
            "https://example.com/post"
        )

    def test_lowercases(self):
        assert normalize_url("HTTPS://EXAMPLE.COM/Post") == ("https://example.com/post")


class TestFindDefaultProfile:
    def test_finds_profile_with_places_db(self, tmp_path):
        profile_dir = tmp_path / "abc123.default"
        profile_dir.mkdir()
        (profile_dir / "places.sqlite").touch()

        result = find_default_profile(str(tmp_path))
        assert result == profile_dir

    def test_reads_profiles_ini(self, tmp_path):
        profile_dir = tmp_path / "myprofile.default-release"
        profile_dir.mkdir()
        (profile_dir / "places.sqlite").touch()

        ini_content = (
            "[Profile0]\n"
            "Name=default-release\n"
            f"Path={profile_dir.name}\n"
            "IsRelative=1\n"
            "Default=1\n"
        )
        (tmp_path / "profiles.ini").write_text(ini_content)

        result = find_default_profile(str(tmp_path))
        assert result == profile_dir

    def test_returns_none_for_empty_dir(self, tmp_path):
        result = find_default_profile(str(tmp_path))
        assert result is None

    def test_reads_install_section(self, tmp_path):
        profile_dir = tmp_path / "xyz.default-release"
        profile_dir.mkdir()
        (profile_dir / "places.sqlite").touch()

        ini_content = (
            "[Profile0]\n"
            "Name=default-release\n"
            f"Path={profile_dir.name}\n"
            "IsRelative=1\n"
            "\n"
            "[Install12345]\n"
            f"Default={profile_dir.name}\n"
        )
        (tmp_path / "profiles.ini").write_text(ini_content)

        result = find_default_profile(str(tmp_path))
        assert result == profile_dir


class TestQueryHistory:
    def _create_test_db(self, db_path: Path, urls_and_days: list[tuple[str, int]]):
        """Create a test places.sqlite with given URLs visited N days ago."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE moz_places (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE moz_historyvisits (
                id INTEGER PRIMARY KEY,
                place_id INTEGER NOT NULL,
                visit_date INTEGER NOT NULL
            )
            """)

        now = datetime.now(tz=timezone.utc)
        for i, (url, days_ago) in enumerate(urls_and_days, 1):
            visit_time = now - timedelta(days=days_ago)
            visit_us = int(visit_time.timestamp() * 1_000_000)
            conn.execute("INSERT INTO moz_places (id, url) VALUES (?, ?)", (i, url))
            conn.execute(
                "INSERT INTO moz_historyvisits (place_id, visit_date) VALUES (?, ?)",
                (i, visit_us),
            )

        conn.commit()
        conn.close()

    def test_returns_recent_urls(self, tmp_path):
        db_path = tmp_path / "places.sqlite"
        self._create_test_db(
            db_path,
            [
                ("https://example.com/post1", 1),  # 1 day ago - within range
                ("https://example.com/post2", 5),  # 5 days ago - within range
                ("https://example.com/post3", 40),  # 40 days ago - outside range
            ],
        )

        result = _query_history(db_path, lookback_days=30)
        assert len(result) == 2
        assert "https://example.com/post1" in result
        assert "https://example.com/post2" in result

    def test_empty_db(self, tmp_path):
        db_path = tmp_path / "places.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE moz_historyvisits "
            "(id INTEGER PRIMARY KEY, place_id INTEGER, visit_date INTEGER)"
        )
        conn.commit()
        conn.close()

        result = _query_history(db_path, lookback_days=30)
        assert result == set()


class TestMarkReadPosts:
    def test_marks_matching_posts(self):
        posts = [
            BlogPost(title="Post 1", author="A", url="https://example.com/post1"),
            BlogPost(title="Post 2", author="B", url="https://example.com/post2"),
            BlogPost(title="Post 3", author="C", url="https://example.com/post3"),
        ]

        visited = {
            "https://example.com/post1",
            "https://example.com/post3",
        }

        mark_read_posts(posts, visited)

        assert posts[0].is_read is True
        assert posts[1].is_read is False
        assert posts[2].is_read is True

    def test_handles_empty_visited(self):
        posts = [
            BlogPost(title="Post", author="A", url="https://example.com/post"),
        ]
        mark_read_posts(posts, set())
        assert posts[0].is_read is False

    def test_url_normalization_in_matching(self):
        posts = [
            BlogPost(
                title="Post",
                author="A",
                url="https://example.com/post/",
            ),
        ]
        visited = {"https://example.com/post"}
        mark_read_posts(posts, visited)
        assert posts[0].is_read is True


class TestGetVisitedUrls:
    def test_returns_empty_when_no_profile(self, tmp_path):
        result = get_visited_urls(str(tmp_path))
        assert result == set()
