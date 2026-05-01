"""Build an RSS 2.0 feed from data/personal_queue.json.

Output: feed/personal.xml — committed to the repo so GitHub Pages (or any
static host) can serve it for Make.com / Buffer / Zapier to poll.

The body is wrapped in CDATA so LinkedIn-style line breaks survive.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from email.utils import format_datetime
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "personal_queue.json"
OUT = ROOT / "feed" / "personal.xml"

FEED_TITLE = "Dam — AI, Sustainability, Digitalization"
FEED_LINK = "https://github.com/arfadillahda/modulus-linkedin-poster"
FEED_DESC = "Evergreen LinkedIn posts auto-generated for @adamaeraa."


def to_rfc822(iso_ts: str) -> str:
    return format_datetime(dt.datetime.fromisoformat(iso_ts))


def main() -> int:
    queue = json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []
    # Newest first, capped at 50
    items = list(reversed(queue))[:50]

    now_rfc = format_datetime(dt.datetime.now(dt.timezone.utc))
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<rss version="2.0">')
    parts.append("<channel>")
    parts.append(f"<title>{escape(FEED_TITLE)}</title>")
    parts.append(f"<link>{escape(FEED_LINK)}</link>")
    parts.append(f"<description>{escape(FEED_DESC)}</description>")
    parts.append(f"<lastBuildDate>{now_rfc}</lastBuildDate>")

    for it in items:
        guid = it["id"]
        title = it.get("title", "")
        body = it.get("body", "")
        pub = to_rfc822(it["ts"])
        parts.append("<item>")
        parts.append(f"<title>{escape(title)}</title>")
        parts.append(f'<guid isPermaLink="false">{escape(guid)}</guid>')
        parts.append(f"<pubDate>{pub}</pubDate>")
        parts.append(f"<description><![CDATA[{body}]]></description>")
        # Many RSS-to-LinkedIn integrations prefer `content:encoded` for
        # the long body. Provide both for compatibility.
        parts.append(f"<content:encoded><![CDATA[{body}]]></content:encoded>")
        parts.append(f"<category>{escape(it.get('topic', ''))}</category>")
        parts.append(f"<category>{escape(it.get('stage', ''))}</category>")
        parts.append("</item>")

    parts.append("</channel>")
    parts.append("</rss>")

    # Inject the content namespace at the top-level <rss>
    xml = "\n".join(parts).replace(
        '<rss version="2.0">',
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
    )

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(xml, encoding="utf-8")
    print(f"Wrote {OUT} with {len(items)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
