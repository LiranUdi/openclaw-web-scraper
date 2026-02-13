# 🌐 Web Scraper — OpenClaw Skill

A web search and page reading skill for [OpenClaw](https://github.com/openclaw/openclaw). No API keys required.

Search the web via DuckDuckGo, extract readable content from any URL, and browse pages interactively — all powered by Playwright + Chromium for full JavaScript rendering.

## Features

- **Web Search** — DuckDuckGo HTML search with multi-page pagination
- **Page Reader** — Extract clean, structured text from any URL (headless or visible)
- **Persistent Browser** — Open a visible browser session that stays open for interactive browsing
- **Zero API Keys** — Everything runs locally, no accounts or tokens needed
- **JSON Output** — All scripts output structured JSON for easy parsing

## Requirements

- Python 3.8+
- pip packages: `requests`, `beautifulsoup4`, `playwright`
- Chromium (installed via Playwright)

## Installation

### As an OpenClaw Skill

Copy the `web-scraper/` directory into your OpenClaw skills folder:

```bash
cp -r web-scraper/ ~/.nvm/versions/node/$(node -v)/lib/node_modules/openclaw/skills/web-scraper
```

Or install from the `.skill` package if available.

### Standalone

```bash
pip install requests beautifulsoup4 playwright
playwright install chromium
```

## Usage

### 1. Search the Web

```bash
python3 scripts/google_search.py "search term" --pages 3
```

| Flag | Description | Default |
|------|-------------|---------|
| `--pages N` | Number of result pages (~10 results each) | 1 |

**Output:** JSON array of `{title, url, snippet}`

```json
[
  {
    "title": "Example Result",
    "url": "https://example.com",
    "snippet": "A brief description of the page..."
  }
]
```

### 2. Read a Page

```bash
python3 scripts/read_page.py "https://example.com" --max-chars 10000 --visible
```

| Flag | Description | Default |
|------|-------------|---------|
| `--max-chars N` | Maximum characters to extract | 50000 |
| `--visible` | Show browser window (non-headless) | off |

**Output:** JSON `{title, content}`

```json
{
  "title": "Page Title",
  "content": "# Heading\n\nExtracted text in markdown-ish format..."
}
```

### 3. Persistent Browser Session

Open a visible browser window that stays open between commands:

```bash
# Open a page (extracts content and keeps browser open)
python3 scripts/browser_session.py open "https://example.com"

# Navigate to a different URL
python3 scripts/browser_session.py navigate "https://other-site.com"

# Re-extract content from the current page
python3 scripts/browser_session.py extract

# Close the browser
python3 scripts/browser_session.py close
```

The browser runs as a background process — it won't block your terminal or agent session.

## How It Works

- **Search** uses DuckDuckGo's HTML endpoint via `requests` + `BeautifulSoup`. This avoids CAPTCHA issues that affect headless browsers on Google/Bing/DDG's JS frontend.
- **Page reading** uses Playwright + Chromium for full JavaScript rendering, then extracts structured text using a read-only DOM TreeWalker (no DOM mutation, so pages stay intact).
- **Browser sessions** use a Unix socket server pattern — a forked child process keeps the browser alive while the parent returns extracted content immediately.

---

## For AI Agents (OpenClaw / LLM Integration)

This section is for AI agents using this skill programmatically.

### When to Use This Skill

- You need to **search the web** for information
- You need to **read the contents** of a specific URL
- You need to **visually browse** a page and keep it open for the user

### Quick Reference

```bash
# Search
python3 scripts/google_search.py "query" --pages N

# Read (headless, fast)
python3 scripts/read_page.py "https://url" --max-chars N

# Read (visible, stays open)
python3 scripts/browser_session.py open "https://url"
python3 scripts/browser_session.py navigate "https://other-url"
python3 scripts/browser_session.py extract
python3 scripts/browser_session.py close
```

### Typical Workflow

1. **Search** for a topic with `google_search.py`
2. **Pick** relevant URLs from the JSON results
3. **Read** pages with `read_page.py` (headless) or `browser_session.py` (visible)
4. If using browser session, **close** it when done

### Important Notes

- All output is **JSON to stdout**. Parse it with `json.loads()` or pipe through `jq`.
- Search returns ~10 results per page. Use `--pages N` for more.
- `read_page.py` opens and closes the browser each time (stateless).
- `browser_session.py` keeps the browser alive between commands (stateful).
- Use `browser_session.py` when the user wants to **see** the page or when you need to navigate multiple pages in sequence.
- The `--visible` flag on `read_page.py` shows the browser but closes it after extraction.
- Scripts resolve relative to the skill's `scripts/` directory.

### Error Handling

- If `browser_session.py open` fails, check if a session is already running (`close` first).
- Network timeouts default to 15s (search) and 30s (page load).
- If content extraction returns very little text, the fallback uses `innerText` of the entire main element.

## License

MIT
