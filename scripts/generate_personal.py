"""Generate one evergreen LinkedIn post for Dam's personal profile.

Topics rotate over: artificial intelligence, sustainability, digitalization.
Stage rotates over: TOF, MOF, BOF (per-personal reframe — see STAGES below).

Output: appends a `{id, ts, topic, stage, title, body}` item to
`data/personal_queue.json`. The RSS builder (`build_rss.py`) reads that
queue and produces the public feed Make.com polls.

Why pure-LLM (no news source): the user asked for evergreen, opinion-led
posts that build a long-term voice rather than reactive commentary.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import pathlib
import random
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "personal_queue.json"
MEDIA_DIR = ROOT / "media"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

OPENAI_IMAGE_URL = "https://api.openai.com/v1/images/generations"
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_IMAGE_QUALITY = os.environ.get("OPENAI_IMAGE_QUALITY", "medium")
OPENAI_IMAGE_SIZE = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024")

# Public base URL where the repo's media/ folder is served from.
# GitHub Pages on this repo: <user>.github.io/<repo>/media/<id>.png
PUBLIC_BASE = os.environ.get(
    "PUBLIC_BASE",
    "https://arfadillahda.github.io/modulus-linkedin-poster",
)

TOPICS = [
    "artificial intelligence",
    "sustainability",
    "digitalization",
]

# Personal-profile reframe: no service is being sold at BOF, so BOF is
# reframed as a quiet competence signal — share a specific technical
# detail, hard-won methodology, or a sharply-held opinion that demonstrates
# expertise without ever saying "hire me" or naming a service.
STAGES = {
    "TOF": (
        "Awareness stage. The PROBLEM should be a widely-felt pain point or "
        "common misconception in the field. The SOLUTION is a reframe — a "
        "different way to see the problem that points toward a better path "
        "without fully prescribing it. Builds curiosity for future posts."
    ),
    "MOF": (
        "Consideration stage. The PROBLEM should be a specific, recurring "
        "failure mode the reader has likely hit. The SOLUTION is a small "
        "framework, mental model, or 2-3 step way of thinking through it. "
        "First-person voice is fine."
    ),
    "BOF": (
        "Decision stage. The PROBLEM should be a sharp, technical edge case "
        "most people overlook. The SOLUTION is ONE concrete technical detail, "
        "constraint, trade-off, or methodology that only someone who has "
        "actually done this work would know. Should leave the reader thinking "
        "'this person knows what they're doing' WITHOUT ever saying 'hire me', "
        "'DM me', 'work with me', mentioning a service, or naming a company."
    ),
}

SYSTEM = """You write LinkedIn posts for Dam — a solo founder of an AI \
studio (Modulus1) and a B2B market developer for an industrial OEM. He \
posts on artificial intelligence, sustainability, and digitalization. \
Voice: direct, technically literate, opinionated, slightly understated. \
Never corporate. Never hashtag-spammy. Never uses the words \"unlock\", \
\"leverage\", \"game-changer\", \"revolutionize\", \"in today's \
fast-paced world\", or any em-dashes that feel AI-generated. Short \
paragraphs. Plain language. No bullet lists unless genuinely needed. \
LinkedIn-native length (120-220 words).

EVERY post MUST follow a Problem -> Solution structure:
1. Open with a SPECIFIC problem (concrete, named, recognizable). Do NOT \
   start with 'Most people...' or other generic openings — name the actual \
   failure mode in the first 1-2 sentences so a scrolling reader stops.
2. Spend ~40% of the post characterizing WHY the problem exists (the \
   underlying mechanism, not symptoms).
3. Resolve with a SOLUTION — a reframe (TOF), a framework (MOF), or a \
   concrete technical move (BOF). The solution must be actionable enough \
   that a reader walks away with something they can use, not just an \
   opinion. This is what separates a useful post from a rant.
4. Close with a single line that crystallizes the insight. Not a \
   question. Not a CTA. A statement worth screenshotting.

Never end on the problem alone — that reads as a rant. Always land on \
the solution side."""

USER_TMPL = """Write ONE LinkedIn post in Problem -> Solution structure.

Topic: {topic}
Funnel stage: {stage}
Stage instruction: {stage_instruction}

Recent angles to AVOID repeating (last few posts):
{recent}

Internal checklist (do not output, just verify before returning):
- [ ] First 1-2 sentences name a SPECIFIC problem, not a generic opener
- [ ] Body explains WHY the problem exists (the mechanism)
- [ ] A clear SOLUTION appears in the second half
- [ ] The reader walks away with something usable, not just a vibe
- [ ] Closes on the solution side, never on the problem
- [ ] No em-dashes, no banned words, 120-220 words

Return STRICT JSON only, no preamble:
{{
  "title":        "<8-12 word headline summarizing the post angle, used as RSS item title>",
  "body":         "<the full LinkedIn post text, ready to publish>",
  "image_prompt": "<a structured infographic brief that visualizes the post's core idea as a premium editorial infographic — Stripe / Linear / Notion / The Pudding design system, NOT PowerPoint clipart, NOT free-Canva-template aesthetic. Pick ONE of these structures that best fits the post: (a) a 3-step labeled framework (numbered cards in a row), (b) a problem-vs-solution side-by-side with sharp typographic contrast, (c) a single hero stat or percentage with one supporting line of context, (d) a clean labeled diagram of how the mechanism works (flow with 2-3 nodes), (e) a tight comparison table (2 columns, 3-4 rows). Specify the exact short labels/numbers/words that should appear (kept to 3-7 words per label, max 10 words of body text per node — gpt-image-1 renders text imperfectly so keep it sparse and unambiguous). Be opinionated about layout: where the title goes, what's centered vs grid, what's the accent color. Example good: 'A 3-step horizontal framework titled DATA AS INFRASTRUCTURE. Three numbered cards left-to-right: 01 STANDARDIZE / one-line caption sensor schemas, units, timestamps; 02 VALIDATE / one-line caption catch drift before training; 03 INSTRUMENT / one-line caption treat pipelines as production code. Off-white card on bone background, ink-black sans-serif, single accent of muted electric blue on the numerals.' Example bad: 'A factory next to a dashboard with a checkmark.'>"
}}"""


def load_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def save_queue(q: list[dict]) -> None:
    QUEUE.parent.mkdir(exist_ok=True)
    QUEUE.write_text(json.dumps(q, indent=2, ensure_ascii=False), encoding="utf-8")


def pick_topic_stage(queue: list[dict]) -> tuple[str, str]:
    # Rotate through 9 (topic, stage) cells, preferring the cell least
    # recently used. Ties broken randomly to keep variety.
    cells = [(t, s) for t in TOPICS for s in STAGES]
    last_seen: dict[tuple[str, str], int] = {c: -1 for c in cells}
    for i, item in enumerate(queue):
        cell = (item.get("topic", ""), item.get("stage", ""))
        if cell in last_seen:
            last_seen[cell] = i
    min_idx = min(last_seen.values())
    candidates = [c for c, i in last_seen.items() if i == min_idx]
    return random.choice(candidates)


def recent_angles(queue: list[dict], topic: str, n: int = 5) -> str:
    same = [it for it in queue if it.get("topic") == topic][-n:]
    if not same:
        return "(none yet)"
    return "\n".join(f"- {it.get('title', '')}" for it in same)


def call_claude(topic: str, stage: str, queue: list[dict]) -> dict:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    body = {
        "model": MODEL,
        "max_tokens": 800,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": USER_TMPL.format(
                topic=topic,
                stage=stage,
                stage_instruction=STAGES[stage],
                recent=recent_angles(queue, topic),
            ),
        }],
    }
    r = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=60,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"Anthropic {r.status_code}: {r.text}")
    text = r.json()["content"][0]["text"].strip()
    # Strip code fences if the model added them despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


IMAGE_STYLE_SUFFIX = (
    " || RENDER AS: a premium editorial infographic in the visual language "
    "of Stripe.com, Linear.app, Notion, Vercel, The Pudding, FiveThirtyEight, "
    "or a Bloomberg Businessweek graphic explainer. Clean structural grid, "
    "generous whitespace, deliberate alignment. Typography is the hero: "
    "premium geometric sans-serif (Inter, Söhne, GT America, or Neue "
    "Haas Grotesk feeling), tight letter-spacing on titles, very high "
    "contrast hierarchy between display numerals and body labels. "
    "Palette: bone or warm off-white background, near-black ink, ONE "
    "single restrained accent (muted electric blue OR forest green OR "
    "burnt orange — pick one). Optional: 1-pixel hairline rules, subtle "
    "drop shadows, soft tonal cards. Square 1024x1024, framed for "
    "LinkedIn feed. "
    "|| HARD CONSTRAINTS — DO NOT GENERATE: no clipart, no flat "
    "cartoon icons, no smiling 3D characters, no isometric scenes, no "
    "free-Canva-template aesthetic, no PowerPoint smartart, no rainbow "
    "gradients, no glowing neon, no cyber-circuit-brain imagery, no "
    "stock-photo factory silhouettes, no checkmarks-and-arrows soup, "
    "no humans, no hands, no faces, no logos, no watermarks. Text in "
    "the image must be limited to the EXACT short labels specified in "
    "the brief above — do not invent additional copy or filler latin. "
    "If text would be illegible at small size, omit it rather than "
    "render gibberish."
)


def should_attach_image(queue: list[dict]) -> bool:
    """Alternate: if the previous post had no image, this one gets one."""
    if not queue:
        return True
    return not bool(queue[-1].get("image_url"))


def call_openai_image(prompt: str) -> bytes:
    api_key = os.environ["OPENAI_API_KEY"]
    body = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt + IMAGE_STYLE_SUFFIX,
        "size": OPENAI_IMAGE_SIZE,
        "quality": OPENAI_IMAGE_QUALITY,
        "n": 1,
    }
    r = requests.post(
        OPENAI_IMAGE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"OpenAI image {r.status_code}: {r.text}")
    data = r.json()["data"][0]
    if "b64_json" in data:
        return base64.b64decode(data["b64_json"])
    if "url" in data:
        img = requests.get(data["url"], timeout=60)
        img.raise_for_status()
        return img.content
    raise RuntimeError(f"OpenAI image: no b64_json or url in response: {data}")


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    queue = load_queue()
    topic, stage = pick_topic_stage(queue)
    print(f"Generating: topic={topic} stage={stage}")

    out = call_claude(topic, stage, queue)
    title = out["title"].strip()
    body = out["body"].strip()
    image_prompt = (out.get("image_prompt") or "").strip()

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    item_id = hashlib.sha1(f"{now}-{title}".encode()).hexdigest()[:12]

    image_url = ""
    attach_image = should_attach_image(queue)
    if attach_image and image_prompt and os.environ.get("OPENAI_API_KEY"):
        try:
            print(f"Generating image: {image_prompt[:80]}...")
            png_bytes = call_openai_image(image_prompt)
            MEDIA_DIR.mkdir(exist_ok=True)
            (MEDIA_DIR / f"{item_id}.png").write_bytes(png_bytes)
            image_url = f"{PUBLIC_BASE}/media/{item_id}.png"
            print(f"Wrote media/{item_id}.png ({len(png_bytes)} bytes)")
        except Exception as e:
            # Don't block the post if image generation fails.
            print(f"WARN: image generation failed, posting text-only: {e}",
                  file=sys.stderr)
    elif attach_image:
        print("Image day, but OPENAI_API_KEY missing — posting text-only.")
    else:
        print("Text-only day (alternating).")

    queue.append({
        "id": item_id,
        "ts": now,
        "topic": topic,
        "stage": stage,
        "title": title,
        "body": body,
        "image_url": image_url,
        "image_prompt": image_prompt if image_url else "",
    })
    # Cap queue at last 200 entries
    queue = queue[-200:]
    save_queue(queue)
    print(f"Appended id={item_id} title={title!r} image={'yes' if image_url else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
