"""CLI entry point for the blog discovery agent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from blog_agent.config import Settings
from blog_agent.discovery import discover_related_feeds
from blog_agent.feeds import fetch_all_feeds
from blog_agent.firefox_history import get_visited_urls, mark_read_posts
from blog_agent.models import BlogPost

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _format_date(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    now = datetime.now(tz=timezone.utc)
    delta = now - dt
    if delta.days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            return "just now"
        return f"{hours}h ago"
    elif delta.days == 1:
        return "yesterday"
    else:
        return f"{delta.days}d ago"


def _render_posts(posts: list[BlogPost], title: str = "New Blog Posts") -> None:
    """Display posts in a rich table."""
    if not posts:
        console.print("\n[dim]No new posts found.[/dim]\n")
        return

    table = Table(
        title=title,
        show_lines=True,
        title_style="bold cyan",
        border_style="dim",
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Title", style="bold", max_width=55)
    table.add_column("Author / Source", max_width=25)
    table.add_column("Published", justify="center", width=11)
    table.add_column("Comments", justify="right", width=8)
    table.add_column("Read?", justify="center", width=5)
    table.add_column("Link", max_width=50, no_wrap=True)

    for i, post in enumerate(posts, 1):
        read_marker = Text("Yes", style="green") if post.is_read else Text("No")
        title_style = "dim" if post.is_read else ""
        comments_str = str(post.comments) if post.comments is not None else "—"

        table.add_row(
            str(i),
            Text(post.title, style=title_style),
            post.author,
            _format_date(post.published),
            comments_str,
            read_marker,
            post.url,
        )

    console.print()
    console.print(table)
    console.print()

    # Summary line
    unread = sum(1 for p in posts if not p.is_read)
    total = len(posts)
    console.print(
        f"  [bold]{total}[/bold] posts found, "
        f"[bold green]{unread}[/bold green] unread\n"
    )


def _build_settings(
    days: int | None,
    no_history: bool,
    feeds_file: str | None,
    verbose: bool,
) -> Settings:
    """Build Settings from CLI options."""
    _setup_logging(verbose)
    settings = Settings()
    if days is not None:
        settings.lookback_days = days
    if feeds_file:
        settings.feeds_file = feeds_file
    if no_history:
        settings.check_firefox_history = False
    return settings


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Blog Discovery Agent - find new posts from your favorite blogs."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(check)


@cli.command()
@click.option(
    "--days",
    "-d",
    default=None,
    type=int,
    help="Number of days to look back (default: 3).",
)
@click.option(
    "--no-history",
    is_flag=True,
    default=False,
    help="Skip Firefox history check.",
)
@click.option(
    "--discover",
    is_flag=True,
    default=False,
    help="Also discover and show posts from recommended/related blogs.",
)
@click.option(
    "--feeds-file",
    type=click.Path(exists=True),
    default=None,
    help="Path to a JSON file with custom feed sources.",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose logging.")
@click.option(
    "--unread-only",
    "-u",
    is_flag=True,
    default=False,
    help="Show only unread posts.",
)
def check(
    days: int | None,
    no_history: bool,
    discover: bool,
    feeds_file: str | None,
    verbose: bool,
    unread_only: bool,
) -> None:
    """Check feeds and display posts in the terminal (default command)."""
    settings = _build_settings(days, no_history, feeds_file, verbose)
    sources = settings.get_feeds()

    console.print(
        f"\n[bold cyan]Blog Discovery Agent[/bold cyan] — "
        f"checking {len(sources)} feeds "
        f"(last {settings.lookback_days} days)\n"
    )

    # Fetch posts from all feeds
    with console.status("[bold green]Fetching feeds..."):
        posts = fetch_all_feeds(
            sources,
            timeout=settings.request_timeout,
            lookback_days=settings.lookback_days,
        )

    # Check Firefox history
    visited: set[str] = set()
    if settings.check_firefox_history and posts:
        with console.status("[bold green]Checking Firefox history..."):
            visited = get_visited_urls(
                settings.firefox_profile_dir,
                lookback_days=max(settings.lookback_days, 30),
            )
            if visited:
                mark_read_posts(posts, visited)

    # Filter if requested
    display_posts = posts
    if unread_only:
        display_posts = [p for p in posts if not p.is_read]

    _render_posts(display_posts, title="Your Blog Posts")

    # Discovery mode
    if discover:
        console.print("[bold cyan]Discovering related blogs...[/bold cyan]\n")
        with console.status("[bold green]Scanning for recommendations..."):
            new_feeds = discover_related_feeds(
                sources, timeout=settings.request_timeout
            )

        if new_feeds:
            console.print(
                f"  Found [bold]{len(new_feeds)}[/bold] new blogs to explore:\n"
            )
            for i, feed in enumerate(new_feeds, 1):
                tags = ", ".join(feed.tags) if feed.tags else ""
                console.print(f"  {i:3}. [bold]{feed.name}[/bold]")
                console.print(f"       {feed.url}")
                if tags:
                    console.print(f"       [dim]{tags}[/dim]")
            console.print()

            # Fetch posts from discovered feeds too
            with console.status("[bold green]Fetching discovered feeds..."):
                discovered_posts = fetch_all_feeds(
                    new_feeds,
                    timeout=settings.request_timeout,
                    lookback_days=settings.lookback_days,
                )

            if discovered_posts:
                if settings.check_firefox_history and visited:
                    mark_read_posts(discovered_posts, visited)
                if unread_only:
                    discovered_posts = [p for p in discovered_posts if not p.is_read]
                _render_posts(discovered_posts, title="Posts from Discovered Blogs")
        else:
            console.print("  [dim]No new blogs discovered.[/dim]\n")


@cli.command()
@click.option(
    "--days",
    "-d",
    default=None,
    type=int,
    help="Number of days to look back (default: 3).",
)
@click.option(
    "--no-history",
    is_flag=True,
    default=False,
    help="Skip Firefox history check.",
)
@click.option(
    "--feeds-file",
    type=click.Path(exists=True),
    default=None,
    help="Path to a JSON file with custom feed sources.",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose logging.")
@click.option("--port", "-p", default=5000, type=int, help="Port (default: 5000).")
@click.option("--host", "-h", default="127.0.0.1", help="Host (default: 127.0.0.1).")
def web(
    days: int | None,
    no_history: bool,
    feeds_file: str | None,
    verbose: bool,
    port: int,
    host: str,
) -> None:
    """Launch the web UI to browse and filter posts."""
    settings = _build_settings(days, no_history, feeds_file, verbose)

    from blog_agent.web import create_app

    app = create_app(settings)

    console.print(
        f"\n[bold cyan]Blog Discovery Agent[/bold cyan] — "
        f"web UI at [link]http://{host}:{port}[/link]\n"
    )

    app.run(host=host, port=port, debug=verbose)


def main() -> None:
    """Entry point wrapper."""
    cli()


if __name__ == "__main__":
    main()
