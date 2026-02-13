---
name: web-scraper
description: Search the web and read page contents without API keys. Use when you need to search for information via DuckDuckGo (with multi-page support), extract readable text content from any URL, or browse pages interactively with a persistent visible browser session. Page reader uses Playwright + Chromium for full JS rendering.
---

# Web Scraper

Three scripts, zero API keys. All output is JSON.

**Dependencies:** `requests`, `beautifulsoup4`, `playwright` (with Chromium).

Install:
```bash
pip install requests beautifulsoup4 playwright
playwright install chromium
```

## 1. Search the Web

```bash
python3 scripts/google_search.py "search query" --pages N
```

- `--pages N` — number of result pages (default: 1, ~10 results/page)
- Returns JSON array of `{title, url, snippet}`
- Uses DuckDuckGo HTML endpoint (no JS needed, avoids CAPTCHA)

## 2. Read a Page (one-shot)

```bash
python3 scripts/read_page.py "https://example.com" [--max-chars N] [--visible]
```

- `--max-chars N` — limit output length (default: 50000)
- `--visible` — show the browser window (non-headless)
- Returns JSON `{title, content}` with clean markdown-formatted text
- Uses Playwright + Chromium for full JS rendering
- Read-only DOM extraction (page stays intact)

## 3. Persistent Browser Session

Open a page in a visible browser that stays open for interactive use:

```bash
python3 scripts/browser_session.py open "https://example.com"    # Open + extract
python3 scripts/browser_session.py navigate "https://other.com"  # Go to new URL
python3 scripts/browser_session.py extract                        # Re-read current page
python3 scripts/browser_session.py close                          # Close browser
```

- Browser stays open between commands (non-blocking)
- Navigate to new URLs without restarting
- Re-extract content after page changes
- Close when done

## Typical Workflow

1. Search: `python3 scripts/google_search.py "topic" --pages 2`
2. Pick URLs from results
3. Quick read: `python3 scripts/read_page.py "https://..."` for headless extraction
4. Or interactive: `python3 scripts/browser_session.py open "https://..."` to browse visually
