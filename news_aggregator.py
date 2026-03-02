#!/usr/bin/env python3
"""
News Aggregator CLI — Fetches RSS feeds and summarizes them using Gemini AI.

Usage:
    python news_aggregator.py "Summarize today's top tech news"
    python news_aggregator.py "What are the market trends?" --list FINANCE
    python news_aggregator.py "Give me a brief digest" --list all --max-articles 3
"""

import argparse
import html as html_module
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
from dotenv import load_dotenv
from google import genai


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / ".env"
DEFAULT_FEEDS = SCRIPT_DIR / "lists.json"


def load_config(config_path: str) -> dict:
    """Load configuration from .env file."""
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Error: Config file not found: {config_file}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(config_file)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print(
            "Error: GEMINI_API_KEY is not set. "
            f"Please add your API key to {config_file}",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "api_key": api_key,
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    }


def load_feeds(feeds_path: str, feed_list: str) -> list[str]:
    """Load feed URLs from lists.json."""
    feeds_file = Path(feeds_path)
    if not feeds_file.exists():
        print(f"Error: Feeds file not found: {feeds_file}", file=sys.stderr)
        sys.exit(1)

    with open(feeds_file, "r") as f:
        data = json.load(f)

    if feed_list.lower() == "all":
        urls = []
        for key in data:
            urls.extend(data[key])
        return urls

    feed_list_upper = feed_list.upper()
    if feed_list_upper not in data:
        available = ", ".join(data.keys())
        print(
            f"Error: List '{feed_list}' not found in {feeds_file}. "
            f"Available lists: {available}",
            file=sys.stderr,
        )
        sys.exit(1)

    return data[feed_list_upper]


def fetch_feed(url: str, max_articles: int, timeout: int = 10) -> dict:
    """Fetch and parse a single RSS feed. Returns dict with source and articles."""
    try:
        import ssl
        import urllib.request

        headers = {"User-Agent": "NewsAggregator/1.0"}
        req = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        response = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        content = response.read()
        feed = feedparser.parse(content)

        if feed.bozo and not feed.entries:
            return {"url": url, "error": str(feed.bozo_exception), "articles": []}

        source_title = feed.feed.get("title", url)
        articles = []

        for entry in feed.entries[:max_articles]:
            article = {
                "title": entry.get("title", "No title"),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            }

            # Get summary — prefer summary, fall back to description
            summary = entry.get("summary", entry.get("description", ""))
            if summary:
                # Strip HTML tags for cleaner text
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                # Truncate very long summaries
                if len(summary) > 500:
                    summary = summary[:500] + "..."
            article["summary"] = summary

            articles.append(article)

        return {"url": url, "source": source_title, "articles": articles, "error": None}

    except Exception as e:
        return {"url": url, "error": str(e), "articles": []}


def fetch_all_feeds(urls: list[str], max_articles: int, max_workers: int = 10) -> list[dict]:
    """Fetch all feeds concurrently."""
    results = []
    total = len(urls)

    print(f"Fetching {total} RSS feeds...", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(fetch_feed, url, max_articles): url for url in urls
        }

        completed = 0
        for future in as_completed(future_to_url):
            completed += 1
            result = future.result()

            if result["error"]:
                print(
                    f"  [{completed}/{total}] ⚠ Failed: {result['url'][:60]}... — {result['error'][:80]}",
                    file=sys.stderr,
                )
            else:
                article_count = len(result["articles"])
                print(
                    f"  [{completed}/{total}] ✓ {result['source'][:50]} ({article_count} articles)",
                    file=sys.stderr,
                )

            results.append(result)

    return results


def build_news_context(feed_results: list[dict]) -> str:
    """Build a text block from fetched feed data for the AI prompt."""
    sections = []

    for result in feed_results:
        if result["error"] or not result["articles"]:
            continue

        source = result.get("source", result["url"])
        lines = [f"## {source}"]

        for article in result["articles"]:
            lines.append(f"- **{article['title']}**")
            if article["published"]:
                lines.append(f"  Published: {article['published']}")
            if article["summary"]:
                lines.append(f"  {article['summary']}")
            if article["link"]:
                lines.append(f"  Link: {article['link']}")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def parse_date(date_str: str) -> datetime:
    """Try to parse an RSS date string into a datetime object."""
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    # Try RFC 2822 format first (most common in RSS)
    try:
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        pass
    # Try ISO 8601 format
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    return datetime.min.replace(tzinfo=timezone.utc)


def generate_html(feed_results: list[dict], output_path: str) -> None:
    """Generate an HTML file with all articles sorted by date descending."""
    # Collect all articles with their source
    all_articles = []
    for result in feed_results:
        if result["error"] or not result["articles"]:
            continue
        source = result.get("source", result["url"])
        for article in result["articles"]:
            all_articles.append({**article, "source": source})

    # Sort by date descending
    all_articles.sort(key=lambda a: parse_date(a["published"]), reverse=True)

    # Build HTML rows
    rows = []
    for a in all_articles:
        title = html_module.escape(a["title"])
        source = html_module.escape(a["source"])
        summary = html_module.escape(a.get("summary", ""))
        published = html_module.escape(a.get("published", "—"))
        link = html_module.escape(a.get("link", ""))

        title_html = f'<a href="{link}" target="_blank">{title}</a>' if link else title

        rows.append(f"""      <tr>
        <td class="date">{published}</td>
        <td>
          <div class="title">{title_html}</div>
          <div class="source">{source}</div>
          {f'<div class="summary">{summary}</div>' if summary else ''}
        </td>
      </tr>""")

    table_rows = "\n".join(rows)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>News Aggregator</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #f5f5f5;
      color: #333;
      line-height: 1.6;
      padding: 2rem;
    }}
    .container {{ max-width: 960px; margin: 0 auto; }}
    h1 {{
      font-size: 1.8rem;
      margin-bottom: 0.3rem;
      color: #1a1a1a;
    }}
    .meta {{
      color: #888;
      font-size: 0.85rem;
      margin-bottom: 1.5rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    th {{
      background: #fafafa;
      text-align: left;
      padding: 0.75rem 1rem;
      font-weight: 600;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #666;
      border-bottom: 2px solid #eee;
    }}
    td {{
      padding: 0.75rem 1rem;
      border-bottom: 1px solid #f0f0f0;
      vertical-align: top;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover {{ background: #fafbfc; }}
    .date {{
      white-space: nowrap;
      font-size: 0.82rem;
      color: #888;
      min-width: 140px;
    }}
    .title a {{
      color: #1a73e8;
      text-decoration: none;
      font-weight: 500;
    }}
    .title a:hover {{ text-decoration: underline; }}
    .source {{
      font-size: 0.8rem;
      color: #999;
      margin-top: 0.15rem;
    }}
    .summary {{
      font-size: 0.85rem;
      color: #555;
      margin-top: 0.3rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>📰 News Aggregator</h1>
    <p class="meta">{len(all_articles)} articles &middot; Generated {generated_at}</p>
    <table>
      <thead>
        <tr><th>Date</th><th>Article</th></tr>
      </thead>
      <tbody>
{table_rows}
      </tbody>
    </table>
  </div>
</body>
</html>
"""

    Path(output_path).write_text(html_content, encoding="utf-8")
    print(f"HTML output written to: {output_path}", file=sys.stderr)


def query_gemini(config: dict, user_prompt: str, news_context: str) -> str:
    """Send the prompt + news context to Gemini and return the response."""
    client = genai.Client(api_key=config["api_key"])

    full_prompt = (
        f"{user_prompt}\n\n"
        f"Here are the latest news articles from various RSS feeds:\n\n"
        f"{news_context}"
    )

    print(f"\nSending to Gemini ({config['model']})...", file=sys.stderr)

    response = client.models.generate_content(
        model=config["model"],
        contents=full_prompt,
    )
    return response.text


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate RSS news feeds and summarize with Gemini AI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  %(prog)s "Summarize today\'s top tech news"\n'
            '  %(prog)s "What are the market trends?" --list FINANCE\n'
            '  %(prog)s "Give me a brief digest" --list all --max-articles 3\n'
        ),
    )
    parser.add_argument(
        "prompt",
        help="The prompt/question to send to Gemini AI along with the news articles",
    )
    parser.add_argument(
        "--list",
        default="all",
        dest="feed_list",
        help="Which feed list to use from lists.json (e.g. NEWS, FINANCE, all). Default: all",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help=f"Path to .env config file. Default: {DEFAULT_CONFIG}",
    )
    parser.add_argument(
        "--feeds",
        default=str(DEFAULT_FEEDS),
        help=f"Path to feeds JSON file. Default: {DEFAULT_FEEDS}",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=5,
        help="Maximum number of articles to fetch per feed. Default: 5",
    )
    parser.add_argument(
        "--html-out",
        default=None,
        metavar="FILE",
        help="Path to write an HTML file with all articles sorted by date.",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Load feed URLs
    urls = load_feeds(args.feeds, args.feed_list)
    print(f"Selected {len(urls)} feeds from list '{args.feed_list}'.", file=sys.stderr)

    # Fetch all feeds
    start_time = time.time()
    feed_results = fetch_all_feeds(urls, args.max_articles)
    elapsed = time.time() - start_time

    # Build context
    news_context = build_news_context(feed_results)
    total_articles = sum(len(r["articles"]) for r in feed_results if not r["error"])
    failed = sum(1 for r in feed_results if r["error"])

    print(
        f"\nFetched {total_articles} articles from {len(feed_results) - failed} feeds "
        f"({failed} failed) in {elapsed:.1f}s.",
        file=sys.stderr,
    )

    if not news_context.strip():
        print("Error: No articles were fetched. Cannot proceed.", file=sys.stderr)
        sys.exit(1)

    # Generate HTML if requested
    if args.html_out:
        generate_html(feed_results, args.html_out)

    # Query Gemini
    try:
        response = query_gemini(config, args.prompt, news_context)
        print("\n" + response)
    except Exception as e:
        print(f"Error calling Gemini API: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
