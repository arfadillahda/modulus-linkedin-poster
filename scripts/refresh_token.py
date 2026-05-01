"""Refresh the LinkedIn OAuth access token using a stored refresh token.

LinkedIn access tokens last ~60 days; refresh tokens last ~365 days. This
script trades the refresh token for a fresh access token and prints the
new values to stdout in a form the GH Action can capture and write back
into repo secrets via the `gh` CLI.

Required env:
  LI_CLIENT_ID
  LI_CLIENT_SECRET
  LI_REFRESH_TOKEN
"""
from __future__ import annotations

import json
import os
import sys

import requests

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


def main() -> int:
    cid = os.environ["LI_CLIENT_ID"]
    csecret = os.environ["LI_CLIENT_SECRET"]
    rtoken = os.environ["LI_REFRESH_TOKEN"]

    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": rtoken,
            "client_id": cid,
            "client_secret": csecret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code >= 300:
        print(f"Refresh failed {r.status_code}: {r.text}", file=sys.stderr)
        return 1

    data = r.json()
    out = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", rtoken),
        "expires_in": data.get("expires_in"),
    }
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
