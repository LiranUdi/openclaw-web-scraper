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
python3 scripts/read_page.py "https://example.com" --max-chars 10000 --format markdown --timeout 60 --proxy http://proxy:8080
```

| Flag | Description | Default |
|------|-------------|---------|
| `--max-chars N` | Max characters to extract | 50000 |
| `--visible` | Show browser window | off |
| `--format` | `json`, `markdown`, or `text` | json |
| `--no-dismiss` | Skip cookie consent auto-dismiss | off |
| `--timeout N` | Page navigation timeout in seconds | 30 |
| `--wait N` | Post-navigation wait in ms | 1500 |
| `--proxy URL` | Proxy server URL | none |
| `--user-agent UA` | Override User-Agent string | Chrome 120 |

**Output includes:** `url` (final after redirects), `load_time_ms`, `title`, `content`

### 3. Persistent Browser Session

```bash
# Open a page (auto-dismisses cookies, extracts content)
python3 scripts/browser_session.py open "https://example.com" --headless --proxy http://proxy:8080

# Navigate with custom timeouts
python3 scripts/browser_session.py navigate "https://other-site.com" --timeout 60 --wait 2000

# Extract content in different formats
python3 scripts/browser_session.py extract --format markdown
python3 scripts/browser_session.py extract --format text

# Screenshot
python3 scripts/browser_session.py screenshot /tmp/page.png
python3 scripts/browser_session.py screenshot /tmp/full.png --full

# Interaction
python3 scripts/browser_session.py click "Sign In"
python3 scripts/browser_session.py click "#submit-btn"
python3 scripts/browser_session.py type "input[name='q']" "search query" --clear --submit
python3 scripts/browser_session.py scroll down
python3 scripts/browser_session.py scroll "#footer"
python3 scripts/browser_session.py wait 3
python3 scripts/browser_session.py wait ".loading-complete"

# Navigation
python3 scripts/browser_session.py back
python3 scripts/browser_session.py forward
python3 scripts/browser_session.py reload

# Advanced features
python3 scripts/browser_session.py eval "document.querySelector('h1').innerText"
python3 scripts/browser_session.py links
python3 scripts/browser_session.py pdf /tmp/report.pdf
python3 scripts/browser_session.py status

# Search for text in the page
python3 scripts/browser_session.py search "pricing"

# Tab management
python3 scripts/browser_session.py tab new "https://docs.example.com"
python3 scripts/browser_session.py tab list
python3 scripts/browser_session.py tab switch 0
python3 scripts/browser_session.py tab close 1

# Cookie handling
python3 scripts/browser_session.py dismiss-cookies

# Close
python3 scripts/browser_session.py close
```

**New Features:**

- **Typing:** `type` finds elements by CSS selector, placeholder, or label text. Use `--clear` to clear first, `--submit` to press Enter after typing
- **Scrolling:** `scroll down|up|top|bottom` or `scroll <selector>` to scroll element into view
- **Waiting:** `wait N` (seconds) or `wait <selector>` (until element appears, 10s timeout)
- **Navigation:** `back`, `forward`, `reload` for browser history
- **JavaScript:** `eval "code"` executes JS and returns JSON result
- **Link extraction:** `links` returns `[{text, url, isExternal}, ...]`
- **PDF export:** `pdf [path]` saves page as PDF (may require `--headless`)
- **Status:** `status` returns browser state (works even if browser not running)
- **Proxy & User-Agent:** `open --proxy URL --user-agent "Custom UA"`

**Resolution order:**
- **Click:** CSS selector → visible text → button/link role name
- **Type:** CSS selector → placeholder text → label text

**Tab management:** Each tab is independent. `tab new` opens and switches to the new tab. `tab switch` brings a tab to focus. `tab close` closes by index (defaults to active tab).

**Performance tracking:** All navigation responses include `load_time_ms`.

### 4. Download Files

```bash
python3 scripts/download_file.py "https://example.com/report.pdf" --output ~/docs --proxy http://proxy:8080
```

| Flag | Description | Default |
|------|-------------|---------|
| `--output DIR` | Save directory | /tmp/downloads |
| `--filename` | Override filename | auto-detected |
| `--proxy URL` | Proxy server URL | none |
| `--user-agent UA` | Override User-Agent string | Chrome 120 |

**Output includes:** `status`, `path`, `filename`, `size_bytes`, `content_type`, `url`
- For PDFs: `extracted_text` (if pdfplumber/PyPDF2 installed), `extracted_chars`
- If redirected: `redirect_url` (final URL after redirects)

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
python3 scripts/read_page.py "url" --max-chars N --format json|markdown|text --timeout 60 --proxy URL

# Interactive browser (full session)
python3 scripts/browser_session.py open "url" --headless --proxy URL --user-agent "Custom UA"
python3 scripts/browser_session.py click "Button"
python3 scripts/browser_session.py type "input[name='q']" "query" --clear --submit
python3 scripts/browser_session.py scroll down
python3 scripts/browser_session.py wait ".results"
python3 scripts/browser_session.py eval "document.title"
python3 scripts/browser_session.py links
python3 scripts/browser_session.py pdf /tmp/page.pdf
python3 scripts/browser_session.py back
python3 scripts/browser_session.py status
python3 scripts/browser_session.py search "keyword"
python3 scripts/browser_session.py screenshot /path/to/file.png
python3 scripts/browser_session.py tab new "url2"
python3 scripts/browser_session.py tab list
python3 scripts/browser_session.py tab switch 0
python3 scripts/browser_session.py extract --format markdown
python3 scripts/browser_session.py close

# Download
python3 scripts/download_file.py "url" --output /tmp/downloads --proxy URL
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
