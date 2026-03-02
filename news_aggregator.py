#!/usr/bin/env python3
"""
News Aggregator CLI — Fetches RSS feeds and summarizes them using Gemini AI.

Usage:
    python news_aggregator.py "Summarize today's top tech news"
    python news_aggregator.py "What are the market trends?" --list FINANCE
    python news_aggregator.py "Give me a brief digest" --list all --max-articles 3
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def fetch_feed(url: str, max_articles: int) -> dict:
    """Fetch and parse a single RSS feed. Returns dict with source and articles."""
    try:
        feed = feedparser.parse(url)

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
                import re
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

    # Query Gemini
    try:
        response = query_gemini(config, args.prompt, news_context)
        print("\n" + response)
    except Exception as e:
        print(f"Error calling Gemini API: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
