# 📰 AI News Aggregator

A **zero-cost AI-powered news aggregator** written in Python. It fetches RSS feeds concurrently, then uses **Google Gemini AI** to summarize and analyze the articles — no OpenClaw needed, no burning tons of tokens. 😉

## ✨ Features

- 🔄 **Concurrent RSS fetching** — pulls from dozens of feeds in parallel
- 🤖 **Gemini AI summaries** — ask any question about the latest news
- 📂 **Configurable feed lists** — organize feeds into categories (NEWS, FINANCE, etc.)
- 📄 **HTML output** — generate a clean, sortable HTML page of all articles
- ⏱️ **Cron-friendly** — designed to run unattended on a Raspberry Pi or any server
- 🆓 **Zero cost** — uses Google's free-tier Gemini API

## 🛠️ Prerequisites

- Python 3.10+
- A free [Google Gemini API key](https://aistudio.google.com/)

## 📦 Installation

1. **Clone the repository:**

   ```bash
   git clone <repo-url>
   cd news-aggregator
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your API key:**

   Go to [Google AI Studio](https://aistudio.google.com/) and create a new API key, then add it to a `.env` file in the project root:

   ```env
   GEMINI_API_KEY=your-api-key-here
   GEMINI_MODEL=gemini-2.5-flash
   ```

## 🚀 Usage

```bash
python news_aggregator.py "<prompt>" [options]
```

### Arguments

| Argument         | Description                                                      | Default |
| ---------------- | ---------------------------------------------------------------- | ------- |
| `prompt`         | The question or instruction to send to Gemini along with the news | *(required)* |
| `--list`         | Feed list to use from `lists.json` (`NEWS`, `FINANCE`, `all`)    | `all`   |
| `--max-articles` | Max articles to fetch per feed                                   | `5`     |
| `--html-out`     | Path to write an HTML file with all articles sorted by date      | *(none)* |
| `--config`       | Path to `.env` config file                                       | `.env`  |
| `--feeds`        | Path to feeds JSON file                                          | `lists.json` |

### Examples

```bash
# Summarize top tech news (max 3 articles per feed)
python news_aggregator.py "Summarize today's top tech news" --list NEWS --max-articles 3

# Analyze market trends from finance feeds
python news_aggregator.py "What are the market trends?" --list FINANCE

# Generate an HTML report of all news
python news_aggregator.py "Summarize the news" --html-out news.html --list NEWS --max-articles 3

# Fetch from all feed lists
python news_aggregator.py "Give me a brief digest" --list all --max-articles 3
```

## 📋 Feed Lists

Feeds are organized into named lists in `lists.json`. The default configuration includes:

- **NEWS** — Major tech and world news sources (Ars Technica, Wired, TechCrunch, BBC, CNN, The Guardian, NYT, and more)
- **FINANCE** — Financial and market news (Bloomberg, CNBC, MarketWatch, Seeking Alpha, CoinDesk, and more)

You can add your own lists by editing `lists.json`:

```json
{
  "NEWS": ["https://example.com/rss", "..."],
  "FINANCE": ["https://example.com/rss", "..."],
  "MY_CUSTOM_LIST": ["https://your-feed.com/rss"]
}
```

Use `--list all` to fetch from every list at once.

## ⏰ Cron Setup (Raspberry Pi / Linux)

Run the aggregator on a schedule to get automated news summaries:

```bash
crontab -e
```

Add a cron entry (e.g., daily at 8 AM):

```cron
0 8 * * * cd /path/to/news-aggregator && /path/to/news-aggregator/venv/bin/python news_aggregator.py "Summarize the news" --html-out news.html --list NEWS --max-articles 3 > summary.txt 2>&1
```

## 📁 Project Structure

```
.
├── news_aggregator.py   # Main CLI application
├── lists.json           # RSS feed URLs organized by category
├── requirements.txt     # Python dependencies
├── .env                 # API key configuration (not tracked in git)
└── README.md            # This file
```

## 📝 License

This project is provided as-is for personal use.
