# 🌐 Web Scraper — OpenClaw Skill

A web search, page reading, and browser automation skill for [OpenClaw](https://github.com/openclaw/openclaw). No API keys required.

## Features

- **Web Search** — Multi-engine (DuckDuckGo, Brave, Google) with pagination
- **Page Reader** — Extract clean, structured text from any URL with JS rendering
- **Persistent Browser** — Visible browser session with navigate, click, and screenshot
- **File Download** — Download files with auto-detection, PDF text extraction
- **Zero API Keys** — Everything runs locally
- **JSON Output** — All scripts output structured JSON

## Requirements

- Python 3.8+
- `pip install requests beautifulsoup4 playwright`
- `playwright install chromium`
- Optional: `pip install pdfplumber` for PDF text extraction

## Installation

### As an OpenClaw Skill

Copy into your OpenClaw skills directory:

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

**Output:** `[{title, url, snippet}, ...]`

**Engine notes:**
- **duckduckgo** — Most reliable, no CAPTCHA issues
- **brave** — Good alternative with offset-based pagination
- **google** — Often blocked by CAPTCHA; use as last resort

### 2. Read a Page

```bash
python3 scripts/read_page.py "https://example.com" --max-chars 10000 --visible
```

| Flag | Description | Default |
|------|-------------|---------|
| `--max-chars N` | Max characters to extract | 50000 |
| `--visible` | Show browser window | off |

**Output:** `{title, content}`

### 3. Persistent Browser Session

```bash
# Open a page (visible browser stays open)
python3 scripts/browser_session.py open "https://example.com"

# Navigate to a different URL
python3 scripts/browser_session.py navigate "https://other-site.com"

# Re-extract content from current page
python3 scripts/browser_session.py extract

# Take a screenshot
python3 scripts/browser_session.py screenshot /tmp/page.png
python3 scripts/browser_session.py screenshot /tmp/full.png --full

# Click an element (by text, CSS selector, or button/link name)
python3 scripts/browser_session.py click "Sign In"
python3 scripts/browser_session.py click "#submit-btn"
python3 scripts/browser_session.py click "a.nav-link"

# Close the browser
python3 scripts/browser_session.py close
```

Click resolution order:
1. CSS selector match
2. Visible text match (partial)
3. Button or link role match by name

### 4. Download Files

```bash
python3 scripts/download_file.py "https://example.com/report.pdf" --output ~/docs
```

| Flag | Description | Default |
|------|-------------|---------|
| `--output DIR` | Save directory | /tmp/downloads |
| `--filename` | Override filename | auto-detected |

**Output:** `{status, path, filename, size_bytes, content_type}`

For PDFs, also returns `extracted_text` if `pdfplumber` or `PyPDF2` is installed.

**Filename detection order:**
1. `Content-Disposition` header
2. URL path
3. `Content-Type` header fallback

## How It Works

- **Search** uses HTTP requests to DuckDuckGo/Brave/Google HTML endpoints via `requests` + `BeautifulSoup`
- **Page reading** uses Playwright + Chromium with a read-only DOM TreeWalker (no DOM mutation)
- **Browser sessions** use a Unix socket server — a forked child keeps the browser alive while commands return immediately
- **Downloads** stream files to disk with automatic filename detection and optional PDF text extraction

---

## For AI Agents (OpenClaw / LLM Integration)

### When to Use This Skill

- Search the web for current information
- Read/extract content from a specific URL
- Browse a page visually and interact (click, navigate)
- Take screenshots for visual context
- Download and read PDF documents or other files

### Quick Reference

```bash
# Search (pick an engine)
python3 scripts/google_search.py "query" --pages N --engine duckduckgo|brave|google

# Read page (headless, fast)
python3 scripts/read_page.py "https://url" --max-chars N

# Interactive browser
python3 scripts/browser_session.py open "https://url"
python3 scripts/browser_session.py click "Button Text"
python3 scripts/browser_session.py screenshot /tmp/shot.png
python3 scripts/browser_session.py navigate "https://other"
python3 scripts/browser_session.py extract
python3 scripts/browser_session.py close

# Download files
python3 scripts/download_file.py "https://url/file.pdf" --output /tmp/downloads
```

### Workflow Pattern

1. **Search** → get list of URLs
2. **Read** or **Open** → extract content from relevant URLs
3. **Click/Navigate** → interact if needed (login, pagination, etc.)
4. **Screenshot** → capture visual state
5. **Download** → grab linked files (PDFs, CSVs, etc.)
6. **Close** → clean up browser session

### Important Notes

- All output is **JSON to stdout**
- `browser_session.py` is **stateful** — one session at a time
- `read_page.py` is **stateless** — opens/closes browser each call
- Always **close** browser sessions when done
- DuckDuckGo is the most reliable engine; use `brave` as backup
- Scripts are in the `scripts/` directory relative to the skill root

## License

MIT
