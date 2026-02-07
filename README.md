# Blog Discovery Agent

An AI-powered CLI agent that monitors your favorite blogs for new posts, checks
your Firefox history to highlight unread content, and discovers related blogs
you might enjoy.

## Features

- **RSS/Atom feed monitoring** — fetches recent posts from configured blogs
- **Firefox history integration** — automatically detects which posts you've
  already read (Linux, macOS, Windows)
- **Blog discovery** — finds recommended/related blogs via Substack
  recommendations and blogroll pages
- **Rich terminal output** — presents posts in a clean, sortable table with
  title, author, date, likes, and read status
- **Configurable** — custom feeds via JSON file, adjustable lookback window,
  environment variable overrides

## Default Blogs

The agent ships with these blogs pre-configured:

| Blog | Topics |
|------|--------|
| [Marginal Revolution](https://marginalrevolution.com/) | Economics, Culture |
| [Bet On It (Bryan Caplan)](https://www.betonit.ai/) | Economics, Prediction |
| [Cremieux Recueil](https://www.cremieux.xyz/) | Data, Statistics |
| [Astral Codex Ten](https://www.astralcodexten.com/) | Rationality, Science |
| [A Collection of Unmitigated Pedantry](https://acoup.blog/) | History, Military |
| [The Zvi](https://thezvi.substack.com/) | Rationality, AI |
| [Derek Thompson](https://www.derekthompson.org/) | Culture, Economics |

## Quick Start with uv

[uv](https://docs.astral.sh/uv/) is the recommended way to run this project.

### Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Run the agent directly (no install needed)

```bash
# Run with default settings (last 3 days)
uv run blog-agent

# Look back 7 days
uv run blog-agent --days 7

# Show only unread posts
uv run blog-agent --unread-only

# Skip Firefox history check
uv run blog-agent --no-history

# Also discover related blogs
uv run blog-agent --discover

# Verbose logging
uv run blog-agent -v

# Use custom feeds file
uv run blog-agent --feeds-file my_feeds.json
```

### Install into a virtual environment

```bash
# Create venv and install
uv venv
uv pip install -e .

# Run
blog-agent --days 5

# Install with dev dependencies
uv pip install -e ".[dev]"
```

## Configuration

### Environment Variables

All settings can be overridden with environment variables prefixed with
`BLOG_AGENT_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `BLOG_AGENT_LOOKBACK_DAYS` | `3` | Days to look back for new posts |
| `BLOG_AGENT_CHECK_FIREFOX_HISTORY` | `true` | Whether to check Firefox history |
| `BLOG_AGENT_FIREFOX_PROFILE_DIR` | auto-detected | Path to Firefox profiles directory |
| `BLOG_AGENT_FEEDS_FILE` | none | Path to custom feeds JSON file |
| `BLOG_AGENT_REQUEST_TIMEOUT` | `15` | HTTP request timeout in seconds |
| `BLOG_AGENT_MAX_CONCURRENT` | `5` | Max concurrent feed fetches |

### Custom Feeds File

Create a JSON file with your own feeds:

```json
[
  {
    "name": "My Favorite Blog",
    "url": "https://example.com",
    "feed_url": "https://example.com/rss.xml",
    "tags": ["tech", "culture"]
  },
  {
    "name": "Another Blog",
    "url": "https://another.example.com"
  }
]
```

Then run with:

```bash
uv run blog-agent --feeds-file my_feeds.json
```

## Development

### Setup

```bash
# Clone and install dev dependencies
uv venv
uv pip install -e ".[dev]"

# Install pre-commit hooks
uv run pre-commit install
```

### Running Tests

```bash
uv run pytest
uv run pytest --cov=blog_agent       # with coverage
uv run pytest -v                      # verbose
```

### Code Quality

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
uv run pre-commit run --all-files
```

Individual tools:

```bash
uv run black src/ tests/              # code formatting
uv run isort src/ tests/              # import sorting
uv run flake8 src/ tests/             # linting
uv run mypy src/                      # type checking
```

## Architecture

```
src/blog_agent/
├── __init__.py              # Package init
├── main.py                  # CLI entry point (Click + Rich)
├── models.py                # Pydantic data models
├── config.py                # Settings management
├── feeds.py                 # RSS/Atom feed fetching
├── firefox_history.py       # Firefox history reading
└── discovery.py             # Blog discovery engine
```

### How It Works

1. **Feed fetching** — reads RSS/Atom feeds from each configured blog using
   `feedparser` and `httpx`, filtering to posts within the lookback window
2. **History check** — copies Firefox's `places.sqlite` to a temp file (to
   avoid lock conflicts) and queries it for visited URLs
3. **Matching** — normalizes URLs (strips query params, fragments, trailing
   slashes) to match blog post URLs against history
4. **Discovery** — scrapes Substack `/recommendations` pages and blog
   `/blogroll` pages to find related publications
5. **Display** — renders everything in a Rich table sorted by date

## License

MIT
