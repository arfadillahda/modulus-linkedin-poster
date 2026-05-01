"""Post the next unposted insight article to LinkedIn.

Mode is chosen via the LI_MODE env var:
  - LI_MODE=company  -> posts to organization page (urn:li:organization:<LI_ORG_ID>)
  - LI_MODE=personal -> posts to authenticated member (urn:li:person:<LI_PERSON_ID>)

Required env vars:
  LI_ACCESS_TOKEN     OAuth 2.0 access token (rotated by refresh-token workflow)
  LI_MODE             "company" or "personal"
  LI_ORG_ID           LinkedIn org id (company mode only)
  LI_PERSON_ID        LinkedIn member id (personal mode only)

State (which URLs have been posted) lives in state/posted_<mode>.json and is
committed back by the GH Action so dedup survives across runs.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any

import requests

from fetch_insights import fetch_insights

LI_API = "https://api.linkedin.com/v2/ugcPosts"
STATE_DIR = pathlib.Path(__file__).resolve().parent.parent / "state"


def load_state(mode: str) -> dict:
    STATE_DIR.mkdir(exist_ok=True)
    f = STATE_DIR / f"posted_{mode}.json"
    if not f.exists():
        return {"posted_urls": []}
    return json.loads(f.read_text(encoding="utf-8"))


def save_state(mode: str, state: dict) -> None:
    f = STATE_DIR / f"posted_{mode}.json"
    f.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def pick_next(items: list[dict], posted: list[str]) -> dict | None:
    for it in items:
        if it["url"] not in posted:
            return it
    return None


def build_commentary(item: dict, mode: str) -> str:
    title = item.get("title", "").strip()
    summary = (item.get("summary") or "").strip()

    if mode == "personal":
        # Slightly more first-person framing for the founder profile.
        lead = "Wrote something new on the Modulus blog:"
    else:
        lead = "New on Modulus Insights:"

    parts = [lead, "", title]
    if summary:
        parts += ["", summary]
    parts += ["", item["url"]]
    return "\n".join(parts).strip()


def post(item: dict, author_urn: str, token: str) -> dict[str, Any]:
    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": build_commentary(item, os.environ["LI_MODE"])},
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "status": "READY",
                    "originalUrl": item["url"],
                    "title": {"text": item.get("title", "Modulus Insights")[:200]},
                    "description": {"text": (item.get("summary") or "")[:256]},
                }],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    r = requests.post(LI_API, headers=headers, json=payload, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"LinkedIn API {r.status_code}: {r.text}")
    return r.json()


def main() -> int:
    mode = os.environ.get("LI_MODE", "").strip().lower()
    if mode not in {"company", "personal"}:
        print("ERROR: LI_MODE must be 'company' or 'personal'", file=sys.stderr)
        return 2

    token = os.environ.get("LI_ACCESS_TOKEN", "").strip()
    if not token:
        print("ERROR: LI_ACCESS_TOKEN is empty", file=sys.stderr)
        return 2

    if mode == "company":
        org_id = os.environ.get("LI_ORG_ID", "").strip()
        if not org_id:
            print("ERROR: LI_ORG_ID required for company mode", file=sys.stderr)
            return 2
        author_urn = f"urn:li:organization:{org_id}"
    else:
        person_id = os.environ.get("LI_PERSON_ID", "").strip()
        if not person_id:
            print("ERROR: LI_PERSON_ID required for personal mode", file=sys.stderr)
            return 2
        author_urn = f"urn:li:person:{person_id}"

    items = fetch_insights(limit=30)
    if not items:
        print("No insights found on page; nothing to post.")
        return 0

    state = load_state(mode)
    item = pick_next(items, state.get("posted_urls", []))
    if not item:
        print("Nothing new to post — all current insights already posted.")
        return 0

    print(f"Posting to LinkedIn ({mode}): {item['url']}")
    resp = post(item, author_urn, token)
    print(f"Posted. id={resp.get('id')}")

    state.setdefault("posted_urls", []).append(item["url"])
    # Keep the last 200 to avoid unbounded growth
    state["posted_urls"] = state["posted_urls"][-200:]
    save_state(mode, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
