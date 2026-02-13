#!/usr/bin/env python3
"""Extract readable content from a web page using Playwright + Chromium.

Usage:
    python3 read_page.py <url> [--max-chars N] [--visible] [--format FMT] [--no-dismiss]

Flags:
    --max-chars N   Max characters to output (default: 50000)
    --visible       Show browser window (non-headless)
    --format FMT    Output format: json (default), markdown, text
    --no-dismiss    Skip cookie consent auto-dismiss

Outputs content in the requested format.
"""

import argparse
import json
import re
import time

from playwright.sync_api import sync_playwright


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
    for (const sel of selectors) {
        try {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) { el.click(); return { dismissed: true }; }
        } catch(e) {}
    }
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
            if (pat.test(text) && btn.offsetParent !== null) { btn.click(); return { dismissed: true }; }
        }
    }
    return { dismissed: false };
}"""


def format_output(result: dict, fmt: str) -> str:
    if fmt == "text":
        content = result.get("content", "")
        content = re.sub(r'^#+\s+', '', content, flags=re.MULTILINE)
        content = re.sub(r'^- ', '  ', content, flags=re.MULTILINE)
        content = re.sub(r'^> ', '', content, flags=re.MULTILINE)
        return content.strip()
    elif fmt == "markdown":
        return f"# {result.get('title', '')}\n\n{result.get('content', '')}"
    else:
        return json.dumps(result, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Web page reader (Playwright + Chromium)")
    parser.add_argument("url", help="URL to read")
    parser.add_argument("--max-chars", type=int, default=50000, help="Max characters (default: 50000)")
    parser.add_argument("--visible", action="store_true", help="Run in visible (non-headless) mode")
    parser.add_argument("--format", choices=["json", "markdown", "text"], default="json", help="Output format")
    parser.add_argument("--no-dismiss", action="store_true", help="Skip cookie consent auto-dismiss")
    parser.add_argument("--timeout", type=int, default=30, help="Page navigation timeout in seconds (default: 30)")
    parser.add_argument("--wait", type=int, default=1500, help="Post-navigation wait in ms (default: 1500)")
    parser.add_argument("--proxy", help="Proxy URL (e.g., http://proxy:8080)")
    parser.add_argument("--user-agent", help="Override User-Agent string")
    args = parser.parse_args()

    try:
        with sync_playwright() as p:
            launch_options = {"headless": not args.visible}
            if args.proxy:
                launch_options["proxy"] = {"server": args.proxy}
            
            browser = p.chromium.launch(**launch_options)
            
            context_options = {
                "user_agent": args.user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "locale": "en-US",
                "viewport": {"width": 1280, "height": 900},
            }
            
            ctx = browser.new_context(**context_options)
            page = ctx.new_page()
            
            start_time = time.time()
            page.goto(args.url, timeout=args.timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(args.wait)
            load_time_ms = int((time.time() - start_time) * 1000)

            if not args.no_dismiss:
                # Try main frame first, then iframes (EU sites often use iframe consent)
                dismissed = page.evaluate(COOKIE_DISMISS_JS)
                if not dismissed.get("dismissed"):
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        try:
                            r = frame.evaluate(COOKIE_DISMISS_JS)
                            if r.get("dismissed"):
                                break
                        except Exception:
                            pass
                page.wait_for_timeout(500)

            result = page.evaluate(EXTRACT_JS)
            if len(result["content"]) > args.max_chars:
                result["content"] = result["content"][:args.max_chars] + "\n\n[...truncated]"

            # Add metadata
            result["url"] = page.url  # Final URL after redirects
            result["load_time_ms"] = load_time_ms

            print(format_output(result, args.format))
            browser.close()
            
    except Exception as e:
        print(json_error(f"Error reading page: {str(e)}"))


if __name__ == "__main__":
    main()
