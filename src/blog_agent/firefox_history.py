"""Read Firefox browsing history to detect already-read blog posts."""

from __future__ import annotations

import configparser
import logging
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def find_default_profile(firefox_dir: str) -> Path | None:
    """Find the default Firefox profile directory.

    Firefox stores profile info in profiles.ini. We look for the default profile
    or fall back to the first profile with a path.
    """
    firefox_path = Path(firefox_dir)
    profiles_ini = firefox_path / "profiles.ini"

    if not profiles_ini.exists():
        # On some systems the dir directly contains profile folders
        # Try to find any that contain places.sqlite
        if firefox_path.is_dir():
            for child in firefox_path.iterdir():
                if child.is_dir() and (child / "places.sqlite").exists():
                    return child
        logger.debug("profiles.ini not found at %s", profiles_ini)
        return None

    config = configparser.ConfigParser()
    config.read(profiles_ini)

    # Look for the default profile
    default_path = None
    first_path = None

    for section in config.sections():
        if not section.startswith("Profile"):
            continue

        path_value = config.get(section, "Path", fallback=None)
        is_relative = config.getboolean(section, "IsRelative", fallback=True)

        if path_value is None:
            continue

        if is_relative:
            profile_path = firefox_path / path_value
        else:
            profile_path = Path(path_value)

        if first_path is None and profile_path.exists():
            first_path = profile_path

        is_default = config.getboolean(section, "Default", fallback=False)
        if is_default and profile_path.exists():
            default_path = profile_path
            break

    # Also check for [Install*] sections which indicate the default profile
    if default_path is None:
        for section in config.sections():
            if section.startswith("Install"):
                path_value = config.get(section, "Default", fallback=None)
                if path_value:
                    candidate = firefox_path / path_value
                    if candidate.exists():
                        default_path = candidate
                        break

    result = default_path or first_path
    if result:
        logger.debug("Using Firefox profile: %s", result)
    else:
        logger.debug("No Firefox profile found in %s", firefox_dir)
    return result


def _copy_places_db(profile_dir: Path) -> Path | None:
    """Copy places.sqlite to a temp file to avoid locking issues.

    Firefox holds a lock on its database while running. We copy it
    to a temporary location so we can query it safely.
    """
    places_db = profile_dir / "places.sqlite"
    if not places_db.exists():
        logger.debug("places.sqlite not found in %s", profile_dir)
        return None

    tmp_dir = Path(tempfile.mkdtemp(prefix="blog_agent_"))
    tmp_db = tmp_dir / "places.sqlite"

    try:
        shutil.copy2(places_db, tmp_db)
        # Also copy WAL and SHM files if they exist (for consistency)
        for suffix in ("-wal", "-shm"):
            wal = profile_dir / f"places.sqlite{suffix}"
            if wal.exists():
                shutil.copy2(wal, tmp_dir / f"places.sqlite{suffix}")
    except (OSError, PermissionError) as exc:
        logger.warning("Could not copy places.sqlite: %s", exc)
        return None

    return tmp_db


def get_visited_urls(
    firefox_dir: str,
    lookback_days: int = 30,
) -> set[str]:
    """Return a set of URLs visited in Firefox within the lookback period.

    The returned URLs are normalized (scheme + netloc + path, no query/fragment)
    for easier matching against blog post URLs.
    """
    profile_dir = find_default_profile(firefox_dir)
    if profile_dir is None:
        logger.info(
            "No Firefox profile found. History check disabled. "
            "Set BLOG_AGENT_CHECK_FIREFOX_HISTORY=false to suppress this."
        )
        return set()

    tmp_db = _copy_places_db(profile_dir)
    if tmp_db is None:
        return set()

    try:
        return _query_history(tmp_db, lookback_days)
    finally:
        # Clean up temp files
        try:
            tmp_db.unlink(missing_ok=True)
            tmp_db.parent.rmdir()
        except OSError:
            pass


def _query_history(db_path: Path, lookback_days: int) -> set[str]:
    """Query the places.sqlite database for recently visited URLs."""
    # Firefox stores timestamps as microseconds since epoch
    cutoff_us = int(
        (datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)).timestamp()
        * 1_000_000
    )

    visited: set[str] = set()

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute(
            """
            SELECT DISTINCT p.url
            FROM moz_places p
            JOIN moz_historyvisits v ON p.id = v.place_id
            WHERE v.visit_date > ?
            """,
            (cutoff_us,),
        )
        for (url,) in cursor:
            visited.add(normalize_url(url))
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("Error reading Firefox history: %s", exc)

    logger.info("Found %d visited URLs in Firefox history", len(visited))
    return visited


def normalize_url(url: str) -> str:
    """Normalize a URL for comparison: lowercase scheme+host, strip trailing slash."""
    parsed = urlparse(url)
    # Keep scheme + netloc + path, drop query and fragment
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return normalized.rstrip("/").lower()


def mark_read_posts(
    posts: list,
    visited_urls: set[str],
) -> None:
    """Mark posts as read if their URL appears in visited_urls (in-place)."""
    for post in posts:
        if normalize_url(post.url) in visited_urls:
            post.is_read = True
