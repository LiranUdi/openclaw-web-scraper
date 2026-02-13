---
name: web-scraper
description: Search the web and read page contents without API keys. Use when you need to search via DuckDuckGo/Brave/Google (multi-page), extract readable text from URLs, browse interactively with a persistent visible browser (with tabs, click, screenshot, text search), download files/PDFs, or dismiss cookie banners. Supports JSON/markdown/text output. Powered by Playwright + Chromium.
---

# Web Scraper

Four scripts, zero API keys. All output is JSON by default.

**Dependencies:** `requests`, `beautifulsoup4`, `playwright` (with Chromium).
**Optional:** `pdfplumber` or `PyPDF2` for PDF text extraction.

Install: `pip install requests beautifulsoup4 playwright && playwright install chromium`

## 1. Search the Web

```bash
python3 scripts/google_search.py "query" --pages N --engine ENGINE
```

- `--engine` — `duckduckgo` (default), `brave`, or `google`
- Returns `[{title, url, snippet}, ...]`

## 2. Read a Page (one-shot)

```bash
python3 scripts/read_page.py "https://url" [--max-chars N] [--visible] [--format json|markdown|text] [--no-dismiss] [--timeout N] [--wait N] [--proxy URL] [--user-agent UA]
```

- `--format` — `json` (default), `markdown`, or `text`
- `--timeout N` — page navigation timeout in seconds (default: 30)
- `--wait N` — post-navigation wait in ms (default: 1500)
- `--proxy URL` — proxy server URL (e.g., http://proxy:8080)
- `--user-agent UA` — override User-Agent string
- Auto-dismisses cookie consent banners (skip with `--no-dismiss`)
- Returns `url` (final after redirects), `load_time_ms` in JSON output

## 3. Persistent Browser Session

```bash
# Basic actions
python3 scripts/browser_session.py open "https://url" [--headless] [--timeout N] [--wait N] [--proxy URL] [--user-agent UA]
python3 scripts/browser_session.py navigate "https://other" [--timeout N] [--wait N]
python3 scripts/browser_session.py extract [--format FMT]          # Re-read page
python3 scripts/browser_session.py screenshot [path] [--full]      # Save screenshot
python3 scripts/browser_session.py close                           # Close browser

# Interaction
python3 scripts/browser_session.py click "Submit"                  # Click by text/selector
python3 scripts/browser_session.py type "input[name='q']" "query" [--clear] [--submit]
python3 scripts/browser_session.py scroll <down|up|top|bottom|selector>
python3 scripts/browser_session.py wait <seconds|selector>         # Wait for time or element

# Navigation
python3 scripts/browser_session.py back                            # Go back in history
python3 scripts/browser_session.py forward                         # Go forward in history
python3 scripts/browser_session.py reload                          # Reload current page

# Advanced
python3 scripts/browser_session.py eval "document.title"           # Execute JavaScript
python3 scripts/browser_session.py links                           # Extract all page links
python3 scripts/browser_session.py pdf [path]                      # Save page as PDF
python3 scripts/browser_session.py status                          # Get browser status
python3 scripts/browser_session.py search "keyword"                # Search text in page

# Tab management
python3 scripts/browser_session.py tab new "https://url"           # Open new tab
python3 scripts/browser_session.py tab list                        # List all tabs
python3 scripts/browser_session.py tab switch 1                    # Switch to tab index
python3 scripts/browser_session.py tab close [index]               # Close tab

# Cookie handling
python3 scripts/browser_session.py dismiss-cookies                 # Manually dismiss cookies
```

**Key features:**
- Cookie consent auto-dismissed on open/navigate
- Multiple tabs supported — open, switch, close independently
- Search returns matching lines with line numbers
- Extract supports json/markdown/text output
- `type` finds elements by CSS selector, placeholder, or label text
- `scroll` supports directions (up/down/top/bottom) or scroll element into view
- `wait` can wait for time (seconds) or element appearance
- `eval` executes JavaScript and returns JSON result
- `links` extracts all page links with `{text, url, isExternal}` format
- `pdf` saves page as PDF (may require headless mode)
- `status` returns browser state without connecting if not running
- All responses include `load_time_ms` for performance tracking

## 4. Download Files

```bash
python3 scripts/download_file.py "https://example.com/doc.pdf" [--output DIR] [--filename NAME] [--proxy URL] [--user-agent UA]
```

- Auto-detects filename from URL/headers
- PDFs: extracts text if pdfplumber/PyPDF2 installed
- Returns `{status, path, filename, size_bytes, content_type, extracted_text}`
- Includes `redirect_url` if redirected during download
