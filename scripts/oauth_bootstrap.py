"""One-time OAuth authorization-code bootstrap for the LinkedIn API.

Run locally (NOT in CI) to obtain the initial access + refresh tokens.

Usage:
    LI_CLIENT_ID=...  LI_CLIENT_SECRET=...  python scripts/oauth_bootstrap.py

What it does:
    1. Spins up a local HTTP server on http://localhost:8765/callback
    2. Opens the LinkedIn consent page in your browser
    3. Captures the auth code on the redirect
    4. Exchanges the code for {access_token, refresh_token}
    5. Prints them to stdout

You must add `http://localhost:8765/callback` as an authorized redirect URL
in your LinkedIn app's Auth tab BEFORE running this.

Take the printed tokens and put them into:
    gh secret set LI_ACCESS_TOKEN  --body "<access_token>"
    gh secret set LI_REFRESH_TOKEN --body "<refresh_token>"
"""
from __future__ import annotations

import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import requests

REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = " ".join([
    "openid",
    "profile",
    "email",
    "w_member_social",
    "w_organization_social",
    "rw_organization_admin",
])
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

_received: dict[str, str] = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a, **_kw):  # silence default access log
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        _received["code"] = qs.get("code", [""])[0]
        _received["state"] = qs.get("state", [""])[0]
        _received["error"] = qs.get("error_description", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<h1>OK</h1><p>You can close this tab and return to the terminal.</p>"
        )


def main() -> int:
    cid = os.environ.get("LI_CLIENT_ID", "").strip()
    csecret = os.environ.get("LI_CLIENT_SECRET", "").strip()
    if not cid or not csecret:
        print("ERROR: LI_CLIENT_ID and LI_CLIENT_SECRET must be set.", file=sys.stderr)
        return 2

    state = secrets.token_urlsafe(16)
    auth_qs = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    })
    auth_url = f"{AUTH_URL}?{auth_qs}"

    server = http.server.HTTPServer(("127.0.0.1", 8765), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("Opening LinkedIn consent page...")
    print(f"If it doesn't open, paste this URL:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for callback on http://localhost:8765/callback ...")
    while "code" not in _received and "error" not in _received:
        pass
    server.shutdown()

    if _received.get("error"):
        print(f"OAuth error: {_received['error']}", file=sys.stderr)
        return 1
    if _received.get("state") != state:
        print("State mismatch — aborting.", file=sys.stderr)
        return 1

    code = _received["code"]
    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": cid,
            "client_secret": csecret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code >= 300:
        print(f"Token exchange failed {r.status_code}: {r.text}", file=sys.stderr)
        return 1

    data = r.json()
    print()
    print("=" * 60)
    print("SUCCESS — tokens below. Copy into GitHub secrets.")
    print("=" * 60)
    print(json.dumps({
        "access_token":  data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "expires_in":    data.get("expires_in"),
        "scope":         data.get("scope"),
    }, indent=2))
    print()
    print("Next:")
    print(f'  gh secret set LI_ACCESS_TOKEN  --body "{data.get("access_token")}"')
    if data.get("refresh_token"):
        print(f'  gh secret set LI_REFRESH_TOKEN --body "{data.get("refresh_token")}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
