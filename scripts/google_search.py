#!/usr/bin/env python3
"""Web search via DuckDuckGo HTML + optional Playwright for page reading. No API key.

Usage:
    python3 google_search.py "search term" [--pages N] [--visible]

Flags:
    --pages N    Number of result pages to fetch (default: 1, ~10 results each)
    --visible    (reserved for future use — search uses requests, not a browser)

Outputs JSON array of {title, url, snippet} per result.

Note: Uses DuckDuckGo HTML endpoint (requests-based) because Google/Bing
block headless browsers. For page content reading, use read_page.py which
uses Playwright for full JS rendering.
"""

import argparse
import json
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

DDG_URL = "https://html.duckduckgo.com/html/"


def search(query: str, pages: int = 1) -> list[dict]:
    results = []
    form_data = {"q": query}

    for page in range(pages):
        resp = requests.post(DDG_URL, data=form_data, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for res in soup.select(".result"):
            title_el = res.select_one(".result__title a, a.result__a")
            snippet_el = res.select_one(".result__snippet")
            if not title_el:
                continue

            href = title_el.get("href", "")
            if "uddg=" in href:
                href = urllib.parse.unquote(
                    urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
                )

            if href.startswith("http"):
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": href,
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })

        # Find next page form data
        if page < pages - 1:
            next_form = None
            for btn in soup.find_all("input", {"value": "Next"}):
                if btn.parent and btn.parent.name == "form":
                    next_form = btn.parent
                    break
            if not next_form:
                break
            form_data = {}
            for inp in next_form.find_all("input"):
                name = inp.get("name")
                if name:
                    form_data[name] = inp.get("value", "")
            time.sleep(1)

    # Deduplicate
    seen = set()
    deduped = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            deduped.append(r)
    return deduped


def main():
    parser = argparse.ArgumentParser(description="Web search (DuckDuckGo)")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--pages", type=int, default=1, help="Number of result pages (default: 1)")
    parser.add_argument("--visible", action="store_true", help="Reserved for future use")
    args = parser.parse_args()

    results = search(args.query, args.pages)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
