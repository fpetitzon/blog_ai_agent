"""AI-powered digest and suggestion reasons using the Anthropic API.

Requires the ``anthropic`` package and an ``ANTHROPIC_API_KEY`` env var.
Both are optional — AI features degrade gracefully when unavailable.
"""

from __future__ import annotations

import logging
import os

from blog_agent.models import BlogPost, FeedSource

logger = logging.getLogger(__name__)

# Model used for digest generation — fast, high quality, cheap
_MODEL = "claude-sonnet-4-5-20250929"


def _get_client():  # type: ignore[return]
    """Create an Anthropic client, or *None* if unavailable."""
    try:
        import anthropic  # noqa: F811
    except ImportError:
        logger.info("anthropic package not installed — AI features disabled")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set — AI features disabled")
        return None

    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# Digest generation
# ---------------------------------------------------------------------------


def generate_digest(
    posts: list[BlogPost],
    lookback_days: int = 3,
) -> str | None:
    """Generate an AI-powered digest of recent posts.

    Returns the digest text, or *None* if the API is unavailable or
    there are no posts to summarize.
    """
    client = _get_client()
    if client is None or not posts:
        return None

    # Build a compact representation of recent posts (cap at 50)
    lines: list[str] = []
    for p in posts[:50]:
        line = f'- "{p.title}" by {p.author} ({p.source_name})'
        if p.summary:
            line += f": {p.summary[:200]}"
        if p.comments:
            line += f" [{p.comments} comments]"
        lines.append(line)

    prompt = (
        f"You are a knowledgeable blog curator. Here are the blog posts "
        f"published in the last {lookback_days} days from blogs the user "
        f"follows:\n\n" + "\n".join(lines) + "\n\n"
        "Write a concise, engaging digest (3-5 short paragraphs) that:\n"
        "1. Highlights the most interesting or important posts\n"
        "2. Groups related themes across different blogs\n"
        "3. Notes any debates or contrasting perspectives\n"
        "4. Suggests which posts are must-reads and why\n\n"
        "Write in a warm, intelligent tone. Be specific about the content — "
        "don't just list titles."
    )

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.warning("Failed to generate digest: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Suggestion reasons
# ---------------------------------------------------------------------------


def generate_suggestion_reasons(
    suggestions: list[FeedSource],
    liked: list[FeedSource],
    existing_feeds: list[FeedSource],
) -> dict[str, str]:
    """Generate "why you'd like this" reasons for suggested blogs.

    Returns a dict of ``{blog_url: reason_text}``.
    """
    client = _get_client()
    if client is None or not suggestions:
        return {}

    liked_desc = (
        "\n".join(f"- {s.name} (tags: {', '.join(s.tags)})" for s in liked)
        if liked
        else "No blogs liked yet."
    )
    existing_desc = "\n".join(
        f"- {s.name} (tags: {', '.join(s.tags)})" for s in existing_feeds[:10]
    )

    suggestion_lines = [
        f"- {s.name} ({s.url}) [tags: {', '.join(s.tags)}]" for s in suggestions[:15]
    ]

    prompt = (
        "You are a blog recommendation engine. The user currently follows "
        "these blogs:\n"
        + existing_desc
        + "\n\nThey've liked these suggested blogs:\n"
        + liked_desc
        + "\n\nFor each blog below, write a one-sentence reason why this "
        "user would enjoy it. Be specific — reference the overlap with "
        "their interests and what makes this blog unique.\n\n"
        "Blogs to explain:\n"
        + "\n".join(suggestion_lines)
        + "\n\nRespond with exactly one line per blog in the format:\n"
        "BLOG_NAME: reason\n\n"
        "Keep each reason to 1-2 sentences, max 150 characters."
    )

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        reasons: dict[str, str] = {}
        for line in text.strip().split("\n"):
            if ":" not in line:
                continue
            name, _, reason = line.partition(":")
            name = name.strip()
            reason = reason.strip()
            # Match back to a suggestion by name overlap
            for s in suggestions:
                if s.name.lower() in name.lower() or name.lower() in s.name.lower():
                    reasons[s.url] = reason
                    break
        return reasons
    except Exception as exc:
        logger.warning("Failed to generate suggestion reasons: %s", exc)
        return {}
