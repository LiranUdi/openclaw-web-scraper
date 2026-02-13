#!/usr/bin/env python3
"""Persistent browser session that stays open until told to close.

Usage:
    python3 browser_session.py open <url> [--headless] [--timeout N] [--wait N] [--proxy URL] [--user-agent UA]
    python3 browser_session.py navigate <url> [--timeout N] [--wait N]
    python3 browser_session.py extract [--format FMT]           Re-extract content from current page
    python3 browser_session.py screenshot [path] [--full]       Save screenshot
    python3 browser_session.py click <selector_or_text>         Click an element
    python3 browser_session.py type <selector> <text> [--clear] [--submit]
    python3 browser_session.py scroll <down|up|top|bottom|selector>
    python3 browser_session.py wait <seconds|selector>          Wait for time or element
    python3 browser_session.py back                             Go back in history
    python3 browser_session.py forward                          Go forward in history
    python3 browser_session.py reload                           Reload current page
    python3 browser_session.py eval "javascript"                Execute JavaScript
    python3 browser_session.py links                            Extract all links from page
    python3 browser_session.py pdf [path]                       Save page as PDF
    python3 browser_session.py status                           Get browser status
    python3 browser_session.py search <text>                    Search for text in page content
    python3 browser_session.py tab new <url>                    Open URL in new tab
    python3 browser_session.py tab list                         List all open tabs
    python3 browser_session.py tab switch <index>               Switch to tab by index
    python3 browser_session.py tab close [index]                Close tab (current if no index)
    python3 browser_session.py dismiss-cookies                  Manually dismiss cookies
    python3 browser_session.py close                            Close browser

Formats for extract: json (default), markdown, text
"""

import json
import os
import re
import signal
import socket
import struct
import sys
import time

SOCKET_PATH = "/tmp/web-scraper-browser.sock"
PID_FILE = "/tmp/web-scraper-browser.pid"


def json_error(message: str) -> str:
    """Return standardized JSON error format."""
    return json.dumps({"error": message}, indent=2, ensure_ascii=False)

EXTRACT_JS = """() => {
    const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','IFRAME','SVG','NAV','FOOTER','HEADER','ASIDE']);
    const title = document.title || '';
    const mainEl = document.querySelector('article')
        || document.querySelector('main')
        || document.querySelector('[role="main"]')
        || document.querySelector('#content, .content, .post-content, .entry-content')
        || document.body;

    const lines = [];
    const seenText = new Set(); // Track already-output text to prevent duplication
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
        if (!text || seenText.has(text)) continue;
        
        // Only process if this element has no accepted children with text
        const hasAcceptedChildren = Array.from(node.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,td,th,pre,blockquote'))
            .some(child => child.innerText?.trim() && !seenText.has(child.innerText.trim()));
        
        if (!hasAcceptedChildren) {
            seenText.add(text);
            const tag = node.tagName.toLowerCase();
            if (tag.startsWith('h')) lines.push('\\n' + '#'.repeat(parseInt(tag[1])) + ' ' + text + '\\n');
            else if (tag === 'li') lines.push('- ' + text);
            else if (tag === 'blockquote') lines.push('> ' + text);
            else lines.push(text);
        }
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


def run_server(url: str, headless: bool = False, timeout_ms: int = 30000, wait_ms: int = 1500, 
               proxy: str = None, user_agent: str = None):
    from playwright.sync_api import sync_playwright
    import time

    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    pw = sync_playwright().start()
    
    launch_options = {"headless": headless}
    if proxy:
        launch_options["proxy"] = {"server": proxy}
    
    browser = pw.chromium.launch(**launch_options)
    
    context_options = {
        "user_agent": user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "locale": "en-US",
        "viewport": {"width": 1280, "height": 900},
    }
    
    ctx = browser.new_context(**context_options)

    # Track pages (tabs)
    pages = [ctx.new_page()]
    active_idx = 0

    def active_page():
        return pages[active_idx]

    start_time = time.time()
    active_page().goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
    active_page().wait_for_timeout(wait_ms)
    load_time_ms = int((time.time() - start_time) * 1000)

    # Auto-dismiss cookie consent on first load (main frame + iframes)
    dismiss_cookies(active_page())

    result = active_page().evaluate(EXTRACT_JS)
    result["load_time_ms"] = load_time_ms
    with open("/tmp/web-scraper-initial.json", "w") as f:
        json.dump(result, f, ensure_ascii=False)

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    sock.listen(1)
    sock.settimeout(1.0)

    def send_response(connection, data):
        """Send response with 8-byte length prefix."""
        if isinstance(data, str):
            payload = data.encode()
        else:
            payload = json.dumps(data, ensure_ascii=False).encode()
        length = len(payload)
        connection.sendall(struct.pack('>Q', length))  # 8-byte big-endian length
        connection.sendall(payload)

    running = True
    while running:
        try:
            conn, _ = sock.accept()
            data = conn.recv(8192).decode()
            cmd = json.loads(data)
            action = cmd.get("action")

            if action == "close":
                send_response(conn, {"status": "closing"})
                conn.close()
                running = False

            elif action == "navigate":
                nav_timeout = cmd.get("timeout_ms", timeout_ms)
                nav_wait = cmd.get("wait_ms", wait_ms)
                start_time = time.time()
                active_page().goto(cmd["url"], timeout=nav_timeout, wait_until="domcontentloaded")
                active_page().wait_for_timeout(nav_wait)
                load_time_ms = int((time.time() - start_time) * 1000)
                dismiss_cookies(active_page())
                result = active_page().evaluate(EXTRACT_JS)
                mc = cmd.get("max_chars")
                if mc and len(result["content"]) > mc:
                    result["content"] = result["content"][:mc] + "\n\n[...truncated]"
                result["load_time_ms"] = load_time_ms
                send_response(conn, result)
                conn.close()

            elif action == "extract":
                result = active_page().evaluate(EXTRACT_JS)
                mc = cmd.get("max_chars")
                if mc and len(result["content"]) > mc:
                    result["content"] = result["content"][:mc] + "\n\n[...truncated]"
                fmt = cmd.get("format", "json")
                output = format_output(result, fmt) if fmt != "json" else json.dumps(result, ensure_ascii=False)
                send_response(conn, output)
                conn.close()

            elif action == "screenshot":
                path = cmd.get("path", "/tmp/screenshot.png")
                full_page = cmd.get("full_page", False)
                active_page().screenshot(path=path, full_page=full_page)
                send_response(conn, {
                    "status": "saved", "path": path,
                    "url": active_page().url, "title": active_page().title(),
                    "tab": active_idx,
                })
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
                send_response(conn, result)
                conn.close()

            elif action == "type":
                selector = cmd.get("selector", "")
                text = cmd.get("text", "")
                clear_first = cmd.get("clear", False)
                submit_after = cmd.get("submit", False)
                
                typed = False
                element = None
                
                # Try CSS selector first
                try:
                    element = active_page().query_selector(selector)
                    if element:
                        if clear_first:
                            element.fill("")
                        element.click()
                        element.type(text)
                        typed = True
                except Exception:
                    pass
                
                # Try placeholder text
                if not typed:
                    try:
                        element = active_page().get_by_placeholder(selector).first
                        if clear_first:
                            element.fill("")
                        element.click()
                        element.type(text)
                        typed = True
                    except Exception:
                        pass
                
                # Try label text
                if not typed:
                    try:
                        element = active_page().get_by_label(selector).first
                        if clear_first:
                            element.fill("")
                        element.click()
                        element.type(text)
                        typed = True
                    except Exception:
                        pass
                
                # Submit if requested
                if typed and submit_after:
                    try:
                        element.press("Enter")
                    except Exception:
                        pass
                
                result = {
                    "status": "typed" if typed else "not_found", 
                    "selector": selector, 
                    "text": text,
                    "cleared": clear_first,
                    "submitted": submit_after and typed,
                    "url": active_page().url
                }
                send_response(conn, result)
                conn.close()

            elif action == "scroll":
                direction = cmd.get("direction", "down")
                selector = cmd.get("selector", "")
                
                try:
                    if selector:
                        # Scroll element into view
                        element = active_page().query_selector(selector)
                        if element:
                            element.scroll_into_view_if_needed()
                            result = {"status": "scrolled", "action": "element_into_view", "selector": selector}
                        else:
                            result = {"status": "not_found", "selector": selector}
                    else:
                        # Scroll page
                        if direction == "down":
                            active_page().keyboard.press("PageDown")
                        elif direction == "up":
                            active_page().keyboard.press("PageUp")
                        elif direction == "bottom":
                            active_page().keyboard.press("End")
                        elif direction == "top":
                            active_page().keyboard.press("Home")
                        else:
                            result = {"error": "Invalid direction. Use: down, up, top, bottom, or provide selector"}
                            send_response(conn, result)
                            conn.close()
                            continue
                        result = {"status": "scrolled", "action": f"page_{direction}"}
                except Exception as e:
                    result = {"error": f"Scroll failed: {str(e)}"}
                
                send_response(conn, result)
                conn.close()

            elif action == "wait":
                wait_for = cmd.get("wait_for", "")
                wait_time = cmd.get("time", 1.0)
                
                try:
                    if wait_for:
                        # Wait for selector to appear
                        element = active_page().wait_for_selector(wait_for, timeout=10000)
                        result = {"status": "found", "selector": wait_for, "waited_ms": "<=10000"}
                    else:
                        # Wait for time
                        active_page().wait_for_timeout(int(wait_time * 1000))
                        result = {"status": "waited", "time_seconds": wait_time}
                except Exception as e:
                    result = {"error": f"Wait failed: {str(e)}"}
                
                send_response(conn, result)
                conn.close()

            elif action == "back":
                try:
                    active_page().go_back(timeout=10000)
                    result = {"status": "navigated_back", "url": active_page().url}
                except Exception as e:
                    result = {"error": f"Go back failed: {str(e)}"}
                send_response(conn, result)
                conn.close()

            elif action == "forward":
                try:
                    active_page().go_forward(timeout=10000)
                    result = {"status": "navigated_forward", "url": active_page().url}
                except Exception as e:
                    result = {"error": f"Go forward failed: {str(e)}"}
                send_response(conn, result)
                conn.close()

            elif action == "reload":
                try:
                    active_page().reload(timeout=10000)
                    result = {"status": "reloaded", "url": active_page().url}
                except Exception as e:
                    result = {"error": f"Reload failed: {str(e)}"}
                send_response(conn, result)
                conn.close()

            elif action == "eval":
                js_code = cmd.get("code", "")
                try:
                    result_value = active_page().evaluate(js_code)
                    result = {"status": "evaluated", "result": result_value}
                except Exception as e:
                    result = {"error": f"JavaScript evaluation failed: {str(e)}"}
                send_response(conn, result)
                conn.close()

            elif action == "links":
                try:
                    links_js = """() => {
                        const links = [];
                        const seen = new Set();
                        document.querySelectorAll('a[href]').forEach(a => {
                            const href = a.href;
                            const text = a.innerText?.trim() || a.textContent?.trim() || '';
                            if (href && !href.startsWith('javascript:') && !href.startsWith('mailto:') && 
                                !href.startsWith('#') && href !== window.location.href && !seen.has(href)) {
                                seen.add(href);
                                const isExternal = !href.startsWith(window.location.origin);
                                links.push({ text, url: href, isExternal });
                            }
                        });
                        return links;
                    }"""
                    links = active_page().evaluate(links_js)
                    result = {"status": "extracted", "links": links, "count": len(links)}
                except Exception as e:
                    result = {"error": f"Links extraction failed: {str(e)}"}
                send_response(conn, result)
                conn.close()

            elif action == "pdf":
                path = cmd.get("path", "/tmp/page.pdf")
                try:
                    # PDF generation typically requires headless mode or special flags
                    # In headed mode, this may not work depending on the browser
                    active_page().pdf(path=path, format="A4")
                    result = {
                        "status": "saved", 
                        "path": path, 
                        "url": active_page().url,
                        "title": active_page().title()
                    }
                except Exception as e:
                    # If PDF generation fails (e.g., in headed mode), provide helpful error
                    error_msg = str(e)
                    if "headless" in error_msg.lower():
                        error_msg += ". PDF generation typically requires headless mode. Try browser_session.py open --headless"
                    result = {"error": f"PDF generation failed: {error_msg}"}
                send_response(conn, result)
                conn.close()

            elif action == "status":
                try:
                    result = {
                        "status": "running",
                        "url": active_page().url,
                        "title": active_page().title(),
                        "tabs": len(pages),
                        "active_tab": active_idx,
                        "uptime": "N/A"  # Could track start time if needed
                    }
                except Exception:
                    result = {"status": "error", "error": "Could not get browser status"}
                send_response(conn, result)
                conn.close()

            elif action == "dismiss_cookies":
                result = dismiss_cookies(active_page())
                send_response(conn, result)
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
                send_response(conn, {
                    "query": query,
                    "matches": len(matches),
                    "results": matches[:50],  # cap at 50
                    "url": active_page().url,
                })
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
                send_response(conn, result)
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
                send_response(conn, {"tabs": tab_info, "active": active_idx})
                conn.close()

            elif action == "tab_switch":
                idx = cmd.get("index", 0)
                if 0 <= idx < len(pages):
                    active_idx = idx
                    pages[active_idx].bring_to_front()
                    send_response(conn, {
                        "status": "switched", "tab": active_idx,
                        "title": pages[active_idx].title(),
                        "url": pages[active_idx].url,
                    })
                else:
                    send_response(conn, {"error": f"Invalid tab index {idx}. Have {len(pages)} tabs."})
                conn.close()

            elif action == "tab_close":
                idx = cmd.get("index", active_idx)
                if len(pages) <= 1:
                    send_response(conn, {"error": "Cannot close the last tab. Use 'close' to close the browser."})
                elif 0 <= idx < len(pages):
                    pages[idx].close()
                    pages.pop(idx)
                    if active_idx >= len(pages):
                        active_idx = len(pages) - 1
                    elif active_idx > idx:
                        active_idx -= 1
                    pages[active_idx].bring_to_front()
                    send_response(conn, {
                        "status": "tab_closed", "closed_index": idx,
                        "active": active_idx, "total_tabs": len(pages),
                    })
                else:
                    send_response(conn, {"error": f"Invalid tab index {idx}"})
                conn.close()

            else:
                send_response(conn, {"error": f"unknown action: {action}"})
                conn.close()

        except socket.timeout:
            continue
        except Exception as e:
            try:
                send_response(conn, {"error": str(e)})
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
    sock.settimeout(10)  # 10 second timeout
    try:
        sock.connect(SOCKET_PATH)
        sock.sendall(json.dumps(cmd).encode())
        
        # Read length header first (8 bytes big-endian)
        length_data = b""
        while len(length_data) < 8:
            chunk = sock.recv(8 - len(length_data))
            if not chunk:
                raise ConnectionError("Server closed connection while reading length header")
            length_data += chunk
        
        payload_length = struct.unpack('>Q', length_data)[0]
        
        # Read exactly payload_length bytes
        payload = b""
        while len(payload) < payload_length:
            chunk = sock.recv(min(65536, payload_length - len(payload)))
            if not chunk:
                raise ConnectionError("Server closed connection while reading payload")
            payload += chunk
        
        sock.close()
        return payload.decode()
    
    except socket.timeout:
        sock.close()
        return json_error("Request timed out (10s)")
    except Exception as e:
        sock.close()
        return json_error(f"Connection error: {str(e)}")


def main():
    if len(sys.argv) < 2:
        print(json_error("Usage: browser_session.py <open|navigate|extract|screenshot|click|type|scroll|wait|back|forward|reload|eval|links|pdf|status|search|tab|dismiss-cookies|close> [args]"))
        sys.exit(1)

    action = sys.argv[1]

    if action == "open":
        if len(sys.argv) < 3:
            print(json_error("Usage: browser_session.py open <url> [--headless] [--timeout N] [--wait N] [--proxy URL] [--user-agent UA]"))
            sys.exit(1)
        url = sys.argv[2]
        headless = "--headless" in sys.argv
        
        # Parse timeout, wait, proxy, and user-agent flags
        timeout_ms = 30000  # default 30s
        wait_ms = 1500      # default 1.5s
        proxy = None
        user_agent = None
        
        for i, arg in enumerate(sys.argv):
            if arg == "--timeout" and i + 1 < len(sys.argv):
                timeout_ms = int(sys.argv[i + 1]) * 1000
            elif arg == "--wait" and i + 1 < len(sys.argv):
                wait_ms = int(sys.argv[i + 1])
            elif arg == "--proxy" and i + 1 < len(sys.argv):
                proxy = sys.argv[i + 1]
            elif arg == "--user-agent" and i + 1 < len(sys.argv):
                user_agent = sys.argv[i + 1]

        # Check if browser is already running and clean up stale processes
        if os.path.exists(SOCKET_PATH):
            if os.path.exists(PID_FILE):
                try:
                    with open(PID_FILE, 'r') as f:
                        old_pid = int(f.read().strip())
                    # Check if PID is still alive
                    os.kill(old_pid, 0)  # This will raise OSError if process is dead
                    # If we reach here, process is alive
                    print(json_error("Browser session already open. Use 'navigate', 'extract', or 'close'."))
                    sys.exit(1)
                except (OSError, ValueError, FileNotFoundError):
                    # Process is dead or PID file is corrupted, clean up
                    if os.path.exists(SOCKET_PATH):
                        os.remove(SOCKET_PATH)
                    if os.path.exists(PID_FILE):
                        os.remove(PID_FILE)
            else:
                # Socket exists but no PID file, likely stale
                os.remove(SOCKET_PATH)

        pid = os.fork()
        if pid == 0:
            os.setsid()
            sys.stdout = open(os.devnull, "w")
            sys.stderr = open(os.devnull, "w")
            run_server(url, headless, timeout_ms, wait_ms, proxy, user_agent)
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
            print(json_error("Timeout waiting for browser to start"))
            sys.exit(1)

    elif action == "navigate":
        if len(sys.argv) < 3:
            print(json_error("Usage: browser_session.py navigate <url> [--timeout N] [--wait N]"))
            sys.exit(1)
        
        url = sys.argv[2]
        cmd = {"action": "navigate", "url": url, "max_chars": 50000}
        
        # Parse timeout and wait flags  
        for i, arg in enumerate(sys.argv):
            if arg == "--timeout" and i + 1 < len(sys.argv):
                cmd["timeout_ms"] = int(sys.argv[i + 1]) * 1000
            elif arg == "--wait" and i + 1 < len(sys.argv):
                cmd["wait_ms"] = int(sys.argv[i + 1])
                
        print(send_command(cmd))

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
            print(json_error("Usage: browser_session.py click <selector_or_text>"))
            sys.exit(1)
        target = " ".join(a for a in sys.argv[2:] if not a.startswith("--"))
        print(send_command({"action": "click", "target": target}))

    elif action == "type":
        if len(sys.argv) < 4:
            print(json_error("Usage: browser_session.py type <selector> <text> [--clear] [--submit]"))
            sys.exit(1)
        
        selector = sys.argv[2]
        text_parts = []
        clear_first = False
        submit_after = False
        
        for arg in sys.argv[3:]:
            if arg == "--clear":
                clear_first = True
            elif arg == "--submit":
                submit_after = True
            elif not arg.startswith("--"):
                text_parts.append(arg)
        
        text = " ".join(text_parts)
        cmd = {
            "action": "type",
            "selector": selector,
            "text": text,
            "clear": clear_first,
            "submit": submit_after
        }
        print(send_command(cmd))

    elif action == "scroll":
        if len(sys.argv) < 3:
            print(json_error("Usage: browser_session.py scroll <down|up|top|bottom|selector>"))
            sys.exit(1)
        
        direction_or_selector = sys.argv[2]
        if direction_or_selector in ["down", "up", "top", "bottom"]:
            cmd = {"action": "scroll", "direction": direction_or_selector}
        else:
            cmd = {"action": "scroll", "selector": direction_or_selector}
        print(send_command(cmd))

    elif action == "wait":
        if len(sys.argv) < 3:
            print(json_error("Usage: browser_session.py wait <seconds|selector>"))
            sys.exit(1)
        
        wait_target = sys.argv[2]
        try:
            # Try to parse as number
            wait_time = float(wait_target)
            cmd = {"action": "wait", "time": wait_time}
        except ValueError:
            # Treat as selector
            cmd = {"action": "wait", "wait_for": wait_target}
        print(send_command(cmd))

    elif action in ["back", "forward", "reload"]:
        print(send_command({"action": action}))

    elif action == "eval":
        if len(sys.argv) < 3:
            print(json_error("Usage: browser_session.py eval \"javascript_code\""))
            sys.exit(1)
        js_code = " ".join(sys.argv[2:])
        print(send_command({"action": "eval", "code": js_code}))

    elif action == "links":
        print(send_command({"action": "links"}))

    elif action == "pdf":
        path = "/tmp/page.pdf"
        if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
            path = sys.argv[2]
        print(send_command({"action": "pdf", "path": path}))

    elif action == "status":
        # Check if socket exists first - if not, report not running
        if not os.path.exists(SOCKET_PATH):
            print(json.dumps({"status": "not running"}, indent=2, ensure_ascii=False))
        else:
            print(send_command({"action": "status"}))

    elif action == "search":
        if len(sys.argv) < 3:
            print(json_error("Usage: browser_session.py search <text>"))
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        print(send_command({"action": "search", "query": query}))

    elif action == "tab":
        if len(sys.argv) < 3:
            print(json_error("Usage: browser_session.py tab <new|list|switch|close> [args]"))
            sys.exit(1)
        sub = sys.argv[2]
        if sub == "new":
            if len(sys.argv) < 4:
                print(json_error("Usage: browser_session.py tab new <url>"))
                sys.exit(1)
            print(send_command({"action": "tab_new", "url": sys.argv[3]}))
        elif sub == "list":
            print(send_command({"action": "tab_list"}))
        elif sub == "switch":
            if len(sys.argv) < 4:
                print(json_error("Usage: browser_session.py tab switch <index>"))
                sys.exit(1)
            print(send_command({"action": "tab_switch", "index": int(sys.argv[3])}))
        elif sub == "close":
            idx = int(sys.argv[3]) if len(sys.argv) > 3 else -1
            cmd = {"action": "tab_close"}
            if idx >= 0:
                cmd["index"] = idx
            print(send_command(cmd))
        else:
            print(json_error(f"Unknown tab command: {sub}"))
            sys.exit(1)

    elif action == "dismiss-cookies":
        print(send_command({"action": "dismiss_cookies"}))

    elif action == "close":
        print(send_command({"action": "close"}))

    else:
        print(json_error(f"Unknown action: {action}"))
        sys.exit(1)


if __name__ == "__main__":
    main()
