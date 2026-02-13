#!/usr/bin/env python3
"""Extract readable content from a web page using Playwright + Chromium.

Usage:
    python3 read_page.py <url> [--max-chars N] [--visible]

Flags:
    --max-chars N   Max characters to output (default: 50000)
    --visible       Run browser in visible (non-headless) mode

Outputs JSON {title, content} with clean readable text.
"""

import argparse
import json

from playwright.sync_api import sync_playwright

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


def main():
    parser = argparse.ArgumentParser(description="Web page reader (Playwright + Chromium)")
    parser.add_argument("url", help="URL to read")
    parser.add_argument("--max-chars", type=int, default=50000, help="Max characters (default: 50000)")
    parser.add_argument("--visible", action="store_true", help="Run in visible (non-headless) mode")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.visible)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.goto(args.url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        result = page.evaluate(EXTRACT_JS)
        if len(result["content"]) > args.max_chars:
            result["content"] = result["content"][:args.max_chars] + "\n\n[...truncated]"

        print(json.dumps(result, indent=2, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
