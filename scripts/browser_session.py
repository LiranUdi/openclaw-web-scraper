#!/usr/bin/env python3
"""Persistent browser session that stays open until told to close.

Usage:
    python3 browser_session.py open <url>                       Open URL in visible browser, extract content
    python3 browser_session.py navigate <url>                   Go to new URL, extract content
    python3 browser_session.py extract [--format FMT]           Re-extract content from current page
    python3 browser_session.py screenshot [path] [--full]       Save screenshot
    python3 browser_session.py click <selector_or_text>         Click an element
    python3 browser_session.py search <text>                    Search for text in page content
    python3 browser_session.py tab new <url>                    Open URL in new tab
    python3 browser_session.py tab list                         List all open tabs
    python3 browser_session.py tab switch <index>               Switch to tab by index
    python3 browser_session.py tab close [index]                Close tab (current if no index)
    python3 browser_session.py close                            Close browser

Formats for extract: json (default), markdown, text
"""

import json
import os
import re
import signal
import socket
import sys
import time

SOCKET_PATH = "/tmp/web-scraper-browser.sock"
PID_FILE = "/tmp/web-scraper-browser.pid"

EXTRACT_JS = """() => {
    const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','IFRAME','SVG','NAV','FOOTER','HEADER','ASIDE']);
    const title = document.title || '';
    const mainEl = document.querySelector('article')
        || document.querySelector('main')
        || document.querySelector('[role="main"]')
        || document.querySelector('#content, .content, .post-content, .entry-content')
        || document.body;

    const lines = [];
    const walker = document.createTreeWalker(mainEl, NodeFilter.SHOW_ELEMENT, {
        acceptNode(node) {
            if (SKIP.has(node.tagName)) return NodeFilter.FILTER_REJECT;
            const tag = node.tagName.toLowerCase();
            if (['h1','h2','h3','h4','h5','h6','p','li','td','th','pre','blockquote'].includes(tag))
                return NodeFilter.FILTER_ACCEPT;
            return NodeFilter.FILTER_SKIP;
        }
    });
    let node;
    while (node = walker.nextNode()) {
        const text = node.innerText?.trim();
        if (!text) continue;
        const tag = node.tagName.toLowerCase();
        if (tag.startsWith('h')) lines.push('\\n' + '#'.repeat(parseInt(tag[1])) + ' ' + text + '\\n');
        else if (tag === 'li') lines.push('- ' + text);
        else if (tag === 'blockquote') lines.push('> ' + text);
        else lines.push(text);
    }
    let content = lines.join('\\n').trim();
    if (content.length < 200) content = mainEl.innerText || '';
    return { title, content };
}"""

# Common cookie consent selectors and text patterns
COOKIE_DISMISS_JS = """() => {
    const selectors = [
        'button[id*="accept" i]', 'button[id*="consent" i]', 'button[id*="agree" i]',
        'button[class*="accept" i]', 'button[class*="consent" i]', 'button[class*="agree" i]',
        'a[id*="accept" i]', 'a[class*="accept" i]',
        '[data-testid*="accept" i]', '[data-testid*="consent" i]',
        '.cookie-banner button', '.cookie-notice button', '.cookie-popup button',
        '#cookie-banner button', '#cookie-notice button', '#cookie-popup button',
        '.cc-btn.cc-dismiss', '.cc-accept', '#onetrust-accept-btn-handler',
        '.js-cookie-consent-agree', '[aria-label*="accept" i][aria-label*="cookie" i]',
        '[aria-label*="Accept all" i]', '[aria-label*="Accept cookies" i]',
    ];

    // Try selectors first
    for (const sel of selectors) {
        try {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) { el.click(); return { dismissed: true, method: 'selector', selector: sel }; }
        } catch(e) {}
    }

    // Try matching button text
    const patterns = [
        /^accept all$/i, /accept all cookies/i, /accept cookies/i, /accept & close/i,
        /^agree$/i, /agree and continue/i, /agree & continue/i,
        /consent and continue/i, /consent & continue/i,
        /got it/i, /i understand/i, /i agree/i,
        /allow all/i, /allow cookies/i, /allow all cookies/i,
        /^ok$/i, /^okay$/i, /^continue$/i, /^dismiss$/i,
        /accept and close/i, /accept and continue/i,
        /nur notwendige/i, /alle akzeptieren/i, /akzeptieren/i,
        /tout accepter/i, /accepter/i, /accepter et continuer/i,
    ];
    for (const btn of document.querySelectorAll('button, a[role="button"], [role="button"]')) {
        const text = btn.innerText?.trim();
        if (!text || text.length > 50) continue;
        for (const pat of patterns) {
            if (pat.test(text) && btn.offsetParent !== null) {
                btn.click();
                return { dismissed: true, method: 'text', matched: text };
            }
        }
    }

    return { dismissed: false };
}"""


def format_output(result: dict, fmt: str) -> str:
    """Format extraction result based on requested format."""
    if fmt == "text":
        # Strip markdown-ish formatting
        content = result.get("content", "")
        content = re.sub(r'^#+\s+', '', content, flags=re.MULTILINE)
        content = re.sub(r'^- ', '  ', content, flags=re.MULTILINE)
        content = re.sub(r'^> ', '', content, flags=re.MULTILINE)
        return content.strip()
    elif fmt == "markdown":
        return f"# {result.get('title', '')}\n\n{result.get('content', '')}"
    else:  # json
        return json.dumps(result, indent=2, ensure_ascii=False)


def dismiss_cookies(page):
    """Try to dismiss cookie consent in main frame and all iframes."""
    result = page.evaluate(COOKIE_DISMISS_JS)
    if result.get("dismissed"):
        page.wait_for_timeout(500)
        return result
    # Check iframes (many EU sites put consent in an iframe)
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            result = frame.evaluate(COOKIE_DISMISS_JS)
            if result.get("dismissed"):
                page.wait_for_timeout(500)
                return result
        except Exception:
            pass
    return {"dismissed": False}


def run_server(url: str):
    from playwright.sync_api import sync_playwright

    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="en-US",
        viewport={"width": 1280, "height": 900},
    )

    # Track pages (tabs)
    pages = [ctx.new_page()]
    active_idx = 0

    def active_page():
        return pages[active_idx]

    active_page().goto(url, timeout=30000, wait_until="domcontentloaded")
    active_page().wait_for_timeout(1500)

    # Auto-dismiss cookie consent on first load (main frame + iframes)
    dismiss_cookies(active_page())

    result = active_page().evaluate(EXTRACT_JS)
    with open("/tmp/web-scraper-initial.json", "w") as f:
        json.dump(result, f, ensure_ascii=False)

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    sock.listen(1)
    sock.settimeout(1.0)

    running = True
    while running:
        try:
            conn, _ = sock.accept()
            data = conn.recv(8192).decode()
            cmd = json.loads(data)
            action = cmd.get("action")

            if action == "close":
                conn.sendall(json.dumps({"status": "closing"}).encode())
                conn.close()
                running = False

            elif action == "navigate":
                active_page().goto(cmd["url"], timeout=30000, wait_until="domcontentloaded")
                active_page().wait_for_timeout(1500)
                dismiss_cookies(active_page())
                result = active_page().evaluate(EXTRACT_JS)
                mc = cmd.get("max_chars")
                if mc and len(result["content"]) > mc:
                    result["content"] = result["content"][:mc] + "\n\n[...truncated]"
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
                conn.close()

            elif action == "extract":
                result = active_page().evaluate(EXTRACT_JS)
                mc = cmd.get("max_chars")
                if mc and len(result["content"]) > mc:
                    result["content"] = result["content"][:mc] + "\n\n[...truncated]"
                fmt = cmd.get("format", "json")
                output = format_output(result, fmt) if fmt != "json" else json.dumps(result, ensure_ascii=False)
                conn.sendall(output.encode())
                conn.close()

            elif action == "screenshot":
                path = cmd.get("path", "/tmp/screenshot.png")
                full_page = cmd.get("full_page", False)
                active_page().screenshot(path=path, full_page=full_page)
                conn.sendall(json.dumps({
                    "status": "saved", "path": path,
                    "url": active_page().url, "title": active_page().title(),
                    "tab": active_idx,
                }).encode())
                conn.close()

            elif action == "click":
                target = cmd.get("target", "")
                clicked = False
                try:
                    el = active_page().query_selector(target)
                    if el:
                        el.click()
                        clicked = True
                except Exception:
                    pass
                if not clicked:
                    try:
                        active_page().get_by_text(target, exact=False).first.click()
                        clicked = True
                    except Exception:
                        pass
                if not clicked:
                    try:
                        active_page().get_by_role("button", name=target).or_(
                            active_page().get_by_role("link", name=target)
                        ).first.click()
                        clicked = True
                    except Exception:
                        pass
                active_page().wait_for_timeout(1000)
                result = {"status": "clicked" if clicked else "not_found", "target": target, "url": active_page().url}
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
                conn.close()

            elif action == "dismiss_cookies":
                result = dismiss_cookies(active_page())
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
                conn.close()

            elif action == "search":
                query = cmd.get("query", "").lower()
                result = active_page().evaluate(EXTRACT_JS)
                content = result.get("content", "")
                lines = content.split("\n")
                matches = []
                for i, line in enumerate(lines):
                    if query in line.lower():
                        matches.append({"line": i + 1, "text": line.strip()})
                conn.sendall(json.dumps({
                    "query": query,
                    "matches": len(matches),
                    "results": matches[:50],  # cap at 50
                    "url": active_page().url,
                }, ensure_ascii=False).encode())
                conn.close()

            elif action == "tab_new":
                new_page = ctx.new_page()
                pages.append(new_page)
                active_idx = len(pages) - 1
                new_page.goto(cmd["url"], timeout=30000, wait_until="domcontentloaded")
                new_page.wait_for_timeout(1500)
                dismiss_cookies(new_page)
                result = new_page.evaluate(EXTRACT_JS)
                result["tab"] = active_idx
                result["total_tabs"] = len(pages)
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
                conn.close()

            elif action == "tab_list":
                tab_info = []
                for i, p in enumerate(pages):
                    try:
                        tab_info.append({
                            "index": i,
                            "title": p.title(),
                            "url": p.url,
                            "active": i == active_idx,
                        })
                    except Exception:
                        tab_info.append({"index": i, "title": "(closed)", "url": "", "active": i == active_idx})
                conn.sendall(json.dumps({"tabs": tab_info, "active": active_idx}, ensure_ascii=False).encode())
                conn.close()

            elif action == "tab_switch":
                idx = cmd.get("index", 0)
                if 0 <= idx < len(pages):
                    active_idx = idx
                    pages[active_idx].bring_to_front()
                    conn.sendall(json.dumps({
                        "status": "switched", "tab": active_idx,
                        "title": pages[active_idx].title(),
                        "url": pages[active_idx].url,
                    }, ensure_ascii=False).encode())
                else:
                    conn.sendall(json.dumps({"error": f"Invalid tab index {idx}. Have {len(pages)} tabs."}).encode())
                conn.close()

            elif action == "tab_close":
                idx = cmd.get("index", active_idx)
                if len(pages) <= 1:
                    conn.sendall(json.dumps({"error": "Cannot close the last tab. Use 'close' to close the browser."}).encode())
                elif 0 <= idx < len(pages):
                    pages[idx].close()
                    pages.pop(idx)
                    if active_idx >= len(pages):
                        active_idx = len(pages) - 1
                    elif active_idx > idx:
                        active_idx -= 1
                    pages[active_idx].bring_to_front()
                    conn.sendall(json.dumps({
                        "status": "tab_closed", "closed_index": idx,
                        "active": active_idx, "total_tabs": len(pages),
                    }, ensure_ascii=False).encode())
                else:
                    conn.sendall(json.dumps({"error": f"Invalid tab index {idx}"}).encode())
                conn.close()

            else:
                conn.sendall(json.dumps({"error": f"unknown action: {action}"}).encode())
                conn.close()

        except socket.timeout:
            continue
        except Exception as e:
            try:
                conn.sendall(json.dumps({"error": str(e)}).encode())
                conn.close()
            except Exception:
                pass

    sock.close()
    for f in [SOCKET_PATH, PID_FILE]:
        if os.path.exists(f):
            os.remove(f)
    browser.close()
    pw.stop()


def send_command(cmd: dict) -> str:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_PATH)
    sock.sendall(json.dumps(cmd).encode())
    chunks = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    sock.close()
    return b"".join(chunks).decode()


def main():
    if len(sys.argv) < 2:
        print("Usage: browser_session.py <open|navigate|extract|screenshot|click|search|tab|close> [args]")
        sys.exit(1)

    action = sys.argv[1]

    if action == "open":
        if len(sys.argv) < 3:
            print("Usage: browser_session.py open <url>")
            sys.exit(1)
        url = sys.argv[2]

        if os.path.exists(SOCKET_PATH):
            print(json.dumps({"error": "Browser session already open. Use 'navigate', 'extract', or 'close'."}))
            sys.exit(1)

        pid = os.fork()
        if pid == 0:
            os.setsid()
            sys.stdout = open(os.devnull, "w")
            sys.stderr = open(os.devnull, "w")
            run_server(url)
            sys.exit(0)
        else:
            for _ in range(30):
                if os.path.exists("/tmp/web-scraper-initial.json"):
                    time.sleep(0.2)
                    with open("/tmp/web-scraper-initial.json") as f:
                        result = json.load(f)
                    os.remove("/tmp/web-scraper-initial.json")
                    result["status"] = "browser open"
                    result["note"] = "Commands: navigate, extract, screenshot, click, search, tab, close"
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    sys.exit(0)
                time.sleep(0.5)
            print(json.dumps({"error": "Timeout waiting for browser to start"}))
            sys.exit(1)

    elif action == "navigate":
        if len(sys.argv) < 3:
            print("Usage: browser_session.py navigate <url>")
            sys.exit(1)
        print(send_command({"action": "navigate", "url": sys.argv[2], "max_chars": 50000}))

    elif action == "extract":
        fmt = "json"
        if "--format" in sys.argv:
            idx = sys.argv.index("--format")
            if idx + 1 < len(sys.argv):
                fmt = sys.argv[idx + 1]
        print(send_command({"action": "extract", "max_chars": 50000, "format": fmt}))

    elif action == "screenshot":
        path = "/tmp/screenshot.png"
        full_page = "--full" in sys.argv
        for arg in sys.argv[2:]:
            if not arg.startswith("--"):
                path = arg
                break
        print(send_command({"action": "screenshot", "path": path, "full_page": full_page}))

    elif action == "click":
        if len(sys.argv) < 3:
            print("Usage: browser_session.py click <selector_or_text>")
            sys.exit(1)
        target = " ".join(a for a in sys.argv[2:] if not a.startswith("--"))
        print(send_command({"action": "click", "target": target}))

    elif action == "search":
        if len(sys.argv) < 3:
            print("Usage: browser_session.py search <text>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        print(send_command({"action": "search", "query": query}))

    elif action == "tab":
        if len(sys.argv) < 3:
            print("Usage: browser_session.py tab <new|list|switch|close> [args]")
            sys.exit(1)
        sub = sys.argv[2]
        if sub == "new":
            if len(sys.argv) < 4:
                print("Usage: browser_session.py tab new <url>")
                sys.exit(1)
            print(send_command({"action": "tab_new", "url": sys.argv[3]}))
        elif sub == "list":
            print(send_command({"action": "tab_list"}))
        elif sub == "switch":
            if len(sys.argv) < 4:
                print("Usage: browser_session.py tab switch <index>")
                sys.exit(1)
            print(send_command({"action": "tab_switch", "index": int(sys.argv[3])}))
        elif sub == "close":
            idx = int(sys.argv[3]) if len(sys.argv) > 3 else -1
            cmd = {"action": "tab_close"}
            if idx >= 0:
                cmd["index"] = idx
            print(send_command(cmd))
        else:
            print(f"Unknown tab command: {sub}")
            sys.exit(1)

    elif action == "dismiss-cookies":
        print(send_command({"action": "dismiss_cookies"}))

    elif action == "close":
        print(send_command({"action": "close"}))

    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
