"""Fetch latest insight articles from modulus1.co/insights.html.

Returns a list of dicts: {url, title, summary, image}.
Sorted newest-first based on DOM order on the insights page.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

INSIGHTS_URL = "https://modulus1.co/insights.html"
USER_AGENT = "Mozilla/5.0 (compatible; ModulusLinkedInBot/1.0)"


def fetch_insights(limit: int = 20) -> list[dict]:
    r = requests.get(INSIGHTS_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    items: list[dict] = []
    seen: set[str] = set()

    # Strategy: every <a href="insight-*.html"> on the page is an article card.
    for a in soup.select('a[href^="insight-"]'):
        href = a.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)

        url = urljoin(INSIGHTS_URL, href)
        title = (a.get_text(" ", strip=True) or "").strip()

        # Try to pull a heading inside the card
        h = a.find(["h1", "h2", "h3", "h4"])
        if h:
            title = h.get_text(" ", strip=True)

        # Find a sibling/descendant paragraph for summary
        summary = ""
        p = a.find("p")
        if p:
            summary = p.get_text(" ", strip=True)

        # Image (optional)
        image = ""
        img = a.find("img")
        if img and img.get("src"):
            image = urljoin(INSIGHTS_URL, img["src"])

        items.append({
            "url": url,
            "title": title,
            "summary": summary,
            "image": image,
        })

        if len(items) >= limit:
            break

    return items


def main() -> int:
    items = fetch_insights()
    json.dump(items, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
