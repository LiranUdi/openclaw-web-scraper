# 🌐 Web Scraper — OpenClaw Skill

A web search, page reading, and browser automation skill for [OpenClaw](https://github.com/openclaw/openclaw). No API keys required.

## Features

- **Web Search** — Multi-engine (DuckDuckGo, Brave, Google) with pagination
- **Page Reader** — Extract clean text from any URL with JS rendering
- **Persistent Browser** — Visible browser with tabs, click, screenshot, and text search
- **Cookie Auto-Dismiss** — Automatically clears cookie consent banners
- **File Download** — Download files with auto-detection, PDF text extraction
- **Output Formats** — JSON, markdown, or plain text
- **Zero API Keys** — Everything runs locally
- **JSON Output** — All scripts output structured JSON by default

## Requirements

- Python 3.8+
- `pip install requests beautifulsoup4 playwright`
- `playwright install chromium`
- Optional: `pip install pdfplumber` for PDF text extraction

## Installation

### As an OpenClaw Skill

```bash
cp -r web-scraper/ $(dirname $(which openclaw))/../lib/node_modules/openclaw/skills/web-scraper
```

### Standalone

```bash
git clone https://github.com/LiranUdi/openclaw-web-scraper.git
cd openclaw-web-scraper
pip install requests beautifulsoup4 playwright
playwright install chromium
```

## Usage

### 1. Search the Web

```bash
python3 scripts/google_search.py "search term" --pages 3 --engine brave
```

| Flag | Description | Default |
|------|-------------|---------|
| `--pages N` | Result pages (~10 results each) | 1 |
| `--engine` | `duckduckgo`, `brave`, or `google` | duckduckgo |

**Engine notes:**
- **duckduckgo** — Most reliable, no CAPTCHA
- **brave** — More results per page, broader sources
- **google** — Often blocked by CAPTCHA; last resort

### 2. Read a Page

```bash
python3 scripts/read_page.py "https://example.com" --max-chars 10000 --format markdown
```

| Flag | Description | Default |
|------|-------------|---------|
| `--max-chars N` | Max characters to extract | 50000 |
| `--visible` | Show browser window | off |
| `--format` | `json`, `markdown`, or `text` | json |
| `--no-dismiss` | Skip cookie consent auto-dismiss | off |

### 3. Persistent Browser Session

```bash
# Open a page (auto-dismisses cookies, extracts content)
python3 scripts/browser_session.py open "https://example.com"

# Navigate
python3 scripts/browser_session.py navigate "https://other-site.com"

# Extract content in different formats
python3 scripts/browser_session.py extract --format markdown
python3 scripts/browser_session.py extract --format text

# Screenshot
python3 scripts/browser_session.py screenshot /tmp/page.png
python3 scripts/browser_session.py screenshot /tmp/full.png --full

# Click elements
python3 scripts/browser_session.py click "Sign In"
python3 scripts/browser_session.py click "#submit-btn"

# Search for text in the page
python3 scripts/browser_session.py search "pricing"

# Tab management
python3 scripts/browser_session.py tab new "https://docs.example.com"
python3 scripts/browser_session.py tab list
python3 scripts/browser_session.py tab switch 0
python3 scripts/browser_session.py tab close 1

# Manually dismiss cookie banner
python3 scripts/browser_session.py dismiss-cookies

# Close
python3 scripts/browser_session.py close
```

**Click resolution:** CSS selector → visible text → button/link role name

**Tab management:** Each tab is independent. `tab new` opens and switches to the new tab. `tab switch` brings a tab to focus. `tab close` closes by index (defaults to active tab).

### 4. Download Files

```bash
python3 scripts/download_file.py "https://example.com/report.pdf" --output ~/docs
```

| Flag | Description | Default |
|------|-------------|---------|
| `--output DIR` | Save directory | /tmp/downloads |
| `--filename` | Override filename | auto-detected |

For PDFs, returns `extracted_text` if `pdfplumber` or `PyPDF2` is installed.

## How It Works

- **Search** — HTTP requests to DuckDuckGo/Brave/Google HTML endpoints
- **Page reading** — Playwright + Chromium with read-only DOM TreeWalker (no mutation)
- **Cookie dismiss** — Tries common selectors and button text patterns (Accept All, Got It, etc.)
- **Browser sessions** — Unix socket server; forked child keeps browser alive, commands return immediately
- **Downloads** — Streams to disk with auto filename detection from headers/URL

---

## For AI Agents (OpenClaw / LLM Integration)

### When to Use This Skill

- Search the web for current information
- Read/extract content from a URL
- Browse interactively (click, navigate, tabs)
- Take screenshots for visual context
- Search for specific text within a page
- Download PDFs or other files
- Deal with cookie-walled content

### Quick Reference

```bash
# Search
python3 scripts/google_search.py "query" --pages N --engine duckduckgo|brave|google

# Read (headless, fast)
python3 scripts/read_page.py "url" --max-chars N --format json|markdown|text

# Interactive browser
python3 scripts/browser_session.py open "url"
python3 scripts/browser_session.py click "Button"
python3 scripts/browser_session.py search "keyword"
python3 scripts/browser_session.py screenshot /path/to/file.png
python3 scripts/browser_session.py tab new "url2"
python3 scripts/browser_session.py tab list
python3 scripts/browser_session.py tab switch 0
python3 scripts/browser_session.py extract --format markdown
python3 scripts/browser_session.py close

# Download
python3 scripts/download_file.py "url" --output /tmp/downloads
```

### Workflow Pattern

1. **Search** → get URLs
2. **Read** or **Open** → extract content
3. **Click/Navigate/Tab** → interact as needed
4. **Search** → find specific info in page
5. **Screenshot** → capture visual state
6. **Download** → grab linked files
7. **Close** → clean up

### Important Notes

- All output defaults to **JSON to stdout**; use `--format` for alternatives
- `browser_session.py` is **stateful** with multi-tab support — one session at a time
- `read_page.py` is **stateless** — opens/closes browser each call
- Cookie consent is **auto-dismissed** on open/navigate
- Always **close** browser sessions when done
- Scripts are in `scripts/` relative to the skill root

## License

MIT
