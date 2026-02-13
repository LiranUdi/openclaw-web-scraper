---
name: web-scraper
description: Search the web and read page contents without API keys. Use when you need to search via DuckDuckGo/Brave/Google (multi-page), extract readable text from URLs, browse interactively with a persistent visible browser, take screenshots, click elements, or download files/PDFs. Powered by Playwright + Chromium.
---

# Web Scraper

Four scripts, zero API keys. All output is JSON.

**Dependencies:** `requests`, `beautifulsoup4`, `playwright` (with Chromium).
**Optional:** `pdfplumber` or `PyPDF2` for PDF text extraction.

## 1. Search the Web

```bash
python3 scripts/google_search.py "query" --pages N --engine ENGINE
```

- `--pages N` — result pages to fetch (default: 1, ~10/page)
- `--engine` — `duckduckgo` (default), `brave`, or `google` (often CAPTCHA'd)
- Returns `[{title, url, snippet}, ...]`

## 2. Read a Page (one-shot)

```bash
python3 scripts/read_page.py "https://url" [--max-chars N] [--visible]
```

- `--visible` — show browser window
- Returns `{title, content}` in markdown-formatted text

## 3. Persistent Browser Session

```bash
python3 scripts/browser_session.py open "https://url"          # Open + extract
python3 scripts/browser_session.py navigate "https://other"    # Go to new URL
python3 scripts/browser_session.py extract                      # Re-read page
python3 scripts/browser_session.py screenshot [path] [--full]   # Save screenshot
python3 scripts/browser_session.py click "Submit"               # Click by text
python3 scripts/browser_session.py click "#login-btn"           # Click by selector
python3 scripts/browser_session.py close                        # Close browser
```

- Browser stays open between commands (non-blocking)
- Click accepts CSS selectors, visible text, or button/link names
- Screenshot saves PNG (default: /tmp/screenshot.png), use `--full` for full page

## 4. Download Files

```bash
python3 scripts/download_file.py "https://example.com/doc.pdf" [--output DIR] [--filename NAME]
```

- Auto-detects filename from URL/headers
- For PDFs: extracts text automatically (if pdfplumber/PyPDF2 installed)
- Returns `{status, path, filename, size_bytes, content_type, extracted_text}`

## Typical Workflow

1. Search: `google_search.py "topic" --pages 2`
2. Read results: `read_page.py "https://..."` or open in browser session
3. Download files: `download_file.py "https://...file.pdf"`
4. Screenshot for visual context: `browser_session.py screenshot`
