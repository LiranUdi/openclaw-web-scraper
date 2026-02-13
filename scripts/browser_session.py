#!/usr/bin/env python3
"""Persistent browser session that stays open until told to close.

Usage:
    python3 browser_session.py open <url>                    Open URL in visible browser, extract content
    python3 browser_session.py navigate <url>                Go to new URL, extract content
    python3 browser_session.py extract                       Re-extract content from current page
    python3 browser_session.py screenshot [path]             Save screenshot (default: /tmp/screenshot.png)
    python3 browser_session.py click <selector_or_text>      Click an element by CSS selector or text
    python3 browser_session.py close                         Close the browser

The browser runs as a persistent process. Commands are sent via a socket.
"""

import json
import os
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
    page = ctx.new_page()
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    result = page.evaluate(EXTRACT_JS)
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
            data = conn.recv(4096).decode()
            cmd = json.loads(data)
            action = cmd.get("action")

            if action == "close":
                conn.sendall(json.dumps({"status": "closing"}).encode())
                conn.close()
                running = False

            elif action == "navigate":
                page.goto(cmd["url"], timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                result = page.evaluate(EXTRACT_JS)
                mc = cmd.get("max_chars")
                if mc and len(result["content"]) > mc:
                    result["content"] = result["content"][:mc] + "\n\n[...truncated]"
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
                conn.close()

            elif action == "extract":
                result = page.evaluate(EXTRACT_JS)
                mc = cmd.get("max_chars")
                if mc and len(result["content"]) > mc:
                    result["content"] = result["content"][:mc] + "\n\n[...truncated]"
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
                conn.close()

            elif action == "screenshot":
                path = cmd.get("path", "/tmp/screenshot.png")
                full_page = cmd.get("full_page", False)
                page.screenshot(path=path, full_page=full_page)
                conn.sendall(json.dumps({
                    "status": "saved",
                    "path": path,
                    "url": page.url,
                    "title": page.title(),
                }).encode())
                conn.close()

            elif action == "click":
                target = cmd.get("target", "")
                clicked = False
                # Try CSS selector first
                try:
                    el = page.query_selector(target)
                    if el:
                        el.click()
                        clicked = True
                except Exception:
                    pass
                # Fall back to text-based click
                if not clicked:
                    try:
                        page.get_by_text(target, exact=False).first.click()
                        clicked = True
                    except Exception:
                        pass
                # Fall back to role-based (button/link)
                if not clicked:
                    try:
                        page.get_by_role("button", name=target).or_(
                            page.get_by_role("link", name=target)
                        ).first.click()
                        clicked = True
                    except Exception:
                        pass

                page.wait_for_timeout(1000)
                result = {"status": "clicked" if clicked else "not_found", "target": target, "url": page.url}
                conn.sendall(json.dumps(result, ensure_ascii=False).encode())
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


def send_command(cmd: dict) -> dict:
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
    return json.loads(b"".join(chunks))


def main():
    if len(sys.argv) < 2:
        print("Usage: browser_session.py <open|navigate|extract|screenshot|click|close> [args]")
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
                    result["note"] = "Commands: navigate <url>, extract, screenshot [path], click <target>, close"
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    sys.exit(0)
                time.sleep(0.5)
            print(json.dumps({"error": "Timeout waiting for browser to start"}))
            sys.exit(1)

    elif action == "navigate":
        if len(sys.argv) < 3:
            print("Usage: browser_session.py navigate <url>")
            sys.exit(1)
        result = send_command({"action": "navigate", "url": sys.argv[2], "max_chars": 50000})
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "extract":
        result = send_command({"action": "extract", "max_chars": 50000})
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "screenshot":
        path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/screenshot.png"
        full_page = "--full" in sys.argv
        result = send_command({"action": "screenshot", "path": path, "full_page": full_page})
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "click":
        if len(sys.argv) < 3:
            print("Usage: browser_session.py click <selector_or_text>")
            sys.exit(1)
        target = " ".join(sys.argv[2:])
        result = send_command({"action": "click", "target": target})
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "close":
        result = send_command({"action": "close"})
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
