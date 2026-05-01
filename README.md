# modulus-linkedin-poster

Auto-poster that publishes the latest article from
[modulus1.co/insights.html](https://modulus1.co/insights.html) to LinkedIn on
a cron — both the **Modulus1 Company Page** and **Dam's personal profile**.

## How it works

1. `scripts/fetch_insights.py` scrapes `insights.html` for `<a href="insight-*.html">`
   cards and returns a newest-first list of `{url, title, summary, image}`.
2. `scripts/post_linkedin.py` picks the first article whose URL is not in
   `state/posted_<mode>.json`, posts it via the LinkedIn `ugcPosts` API, and
   appends the URL to state. The workflow then commits the updated state file
   back to the repo so dedup survives across runs.
3. `scripts/refresh_token.py` runs weekly to swap the refresh token for a new
   access token (LinkedIn access tokens expire after ~60 days). The refresh
   workflow writes the new tokens back into repo secrets via `gh secret set`.

## Cron schedule

| Workflow         | Cron (UTC)        | Posts as       |
|------------------|-------------------|----------------|
| `post-company`   | Mon/Wed/Fri 09:00 | Modulus1 Org   |
| `post-personal`  | Tue/Thu 10:00     | Dam (member)   |
| `refresh-token`  | Sun 02:00         | —              |

## Required GitHub Actions secrets

| Secret              | Purpose                                                  |
|---------------------|----------------------------------------------------------|
| `LI_CLIENT_ID`      | LinkedIn app client id                                   |
| `LI_CLIENT_SECRET`  | LinkedIn app client secret                               |
| `LI_ACCESS_TOKEN`   | OAuth access token (rotated by `refresh-token.yml`)      |
| `LI_REFRESH_TOKEN`  | OAuth refresh token (rotated by `refresh-token.yml`)     |
| `LI_ORG_ID`         | Numeric LinkedIn organization id (company mode)          |
| `LI_PERSON_ID`      | Numeric LinkedIn member id (personal mode)               |
| `GH_PAT_REPO_ADMIN` | Fine-grained PAT with `secrets:write` on this repo       |

## One-time setup

1. Create a LinkedIn app at <https://www.linkedin.com/developers/apps>.
2. Request products:
   - **Share on LinkedIn** → grants `w_member_social` (personal posts)
   - **Marketing Developer Platform** → grants `w_organization_social`
     (company posts). Approval can take a few days.
3. Run the OAuth authorization-code flow once locally to obtain the initial
   `access_token` + `refresh_token`. Scopes:
   `openid profile email w_member_social w_organization_social rw_organization_admin`.
4. Get your `LI_PERSON_ID` from `GET https://api.linkedin.com/v2/userinfo`
   (the `sub` field) and your `LI_ORG_ID` from
   `GET https://api.linkedin.com/v2/organizationAcls?q=roleAssignee`.
5. Push the seven secrets listed above into the repo.
6. Manually trigger `post-company` and `post-personal` once via
   "Run workflow" to verify.

## Local dry-run

```bash
pip install -r requirements.txt
python scripts/fetch_insights.py | head -50

LI_MODE=company \
LI_ACCESS_TOKEN=... \
LI_ORG_ID=... \
python scripts/post_linkedin.py
```

## State files

- `state/posted_company.json` — URLs already posted to Modulus1 page
- `state/posted_personal.json` — URLs already posted to Dam's profile

Each file holds `{ "posted_urls": [...] }`, capped at the last 200 entries.
