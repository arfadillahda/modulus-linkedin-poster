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

import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import random
import re
import sys

import cairosvg
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "personal_queue.json"
MEDIA_DIR = ROOT / "media"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
SVG_MODEL = os.environ.get("ANTHROPIC_SVG_MODEL", "claude-sonnet-4-6")

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
  "title": "<8-12 word headline summarizing the post angle, used as RSS item title>",
  "body":  "<the full LinkedIn post text, ready to publish>"
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
    return parse_json_loose(text)


def parse_json_loose(text: str) -> dict:
    """Tolerant JSON parser for LLM output.

    Handles: code fences, leading prose, trailing prose, trailing commas
    before } or ]. Falls back to slicing from first { to last }.
    """
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Slice from first { to last } in case model wrapped the JSON in prose.
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Strip trailing commas before } or ]
            import re
            cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
            return json.loads(cleaned)
    raise json.JSONDecodeError("Could not extract JSON object", s, 0)


SVG_SYSTEM = """You are a senior editorial-infographic designer working in \
the visual language of Stripe.com, Linear.app, Notion, Vercel, The Pudding, \
FiveThirtyEight, and Bloomberg Businessweek graphic explainers. You output \
ONLY one self-contained <svg> element — nothing before it, nothing after. \
No prose. No code fences. No markdown. The SVG IS your entire response."""

SVG_USER_TMPL = """Design a square 1024x1024 editorial infographic that \
communicates the core idea of this LinkedIn post.

POST TITLE: {title}

POST BODY:
{body}

DESIGN BRIEF:
- Pick ONE of these layouts that best fits the post's structure (do not \
mix them):
  (a) 3-step framework — three vertical cards in a row, each numbered 01/02/03
  (b) Problem vs Solution — two columns with sharp typographic contrast
  (c) Hero stat — one large display number/percentage with a single \
supporting line of context underneath
  (d) Mechanism diagram — 2-3 connected nodes showing how something works
  (e) Comparison table — 2 columns x 3-4 rows with concise labels
- Decide which layout makes the post's insight clearest. Be opinionated.
- Total on-canvas text MUST be short, specific, and pulled from the post's \
actual ideas. No filler. No lorem ipsum. Total word count on canvas: \
between 12 and 60 words including the title.
- Include a small kicker label at the top (one of: AI / SUSTAINABILITY / \
DIGITALIZATION — match the post's topic) in tracked-out small caps.
- Include a tight headline (5-9 words) that captures the insight.

VISUAL SYSTEM (strict):
- viewBox="0 0 1024 1024"
- Background: warm off-white (#F5F1EA or similar bone tone)
- Ink: near-black (#111111) for headlines, slightly lighter (#3A3A3A) for body
- ONE single restrained accent — pick exactly one of these and use it \
sparingly: muted electric blue (#2D5BFF), forest green (#1F5C3D), or burnt \
orange (#C24A1F)
- Typography stack: font-family="Inter, 'Helvetica Neue', Arial, \
sans-serif". Use font-weight 800 for display, 600 for kickers, 400 for \
body. Letter-spacing tight on display, tracked-out on small caps.
- Optional: 1px hairline rules in #11111122, subtle 2-3% drop shadows on \
cards, soft tonal cards in #EFEAE0.
- Generous whitespace. Deliberate alignment to a 12-column or 8-column grid.

HARD BANS — do NOT include:
- No clipart, no emoji, no cartoon icons, no isometric scenes
- No PowerPoint SmartArt or free-Canva aesthetic
- No rainbow gradients, no glowing neon, no cyber/circuit imagery
- No raster <image>, no <foreignObject>, no external font URLs (@import \
or <link>) — pure SVG primitives only (rect, line, text, path, g, defs, \
filter, clipPath, mask)
- No human figures, no faces, no hands, no logos
- No filler text, no decorative latin, no fake brand names

Output the complete <svg>...</svg> element and nothing else."""


def should_attach_image(queue: list[dict]) -> bool:
    """Alternate: if the previous post had no image, this one gets one."""
    if not queue:
        return True
    return not bool(queue[-1].get("image_url"))


def call_claude_svg(title: str, body: str) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    payload = {
        "model": SVG_MODEL,
        "max_tokens": 8000,
        "system": SVG_SYSTEM,
        "messages": [{
            "role": "user",
            "content": SVG_USER_TMPL.format(title=title, body=body),
        }],
    }
    r = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"Anthropic SVG {r.status_code}: {r.text}")
    text = r.json()["content"][0]["text"].strip()
    # Tolerate accidental code fences.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    # Slice to the <svg>...</svg> bounds in case the model added prose.
    start = text.find("<svg")
    end = text.rfind("</svg>")
    if start == -1 or end == -1:
        raise RuntimeError(f"No <svg> element in response. Got: {text[:200]!r}")
    return text[start:end + len("</svg>")]


def rasterize_svg(svg_markup: str, out_path: pathlib.Path, size: int = 1024) -> None:
    """Render SVG to PNG at the requested square size."""
    png_bytes = cairosvg.svg2png(
        bytestring=svg_markup.encode("utf-8"),
        output_width=size,
        output_height=size,
    )
    out_path.write_bytes(png_bytes)


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

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    item_id = hashlib.sha1(f"{now}-{title}".encode()).hexdigest()[:12]

    image_url = ""
    attach_image = should_attach_image(queue)
    if attach_image:
        try:
            print(f"Generating SVG infographic via {SVG_MODEL}...")
            svg = call_claude_svg(title, body)
            MEDIA_DIR.mkdir(exist_ok=True)
            png_path = MEDIA_DIR / f"{item_id}.png"
            svg_path = MEDIA_DIR / f"{item_id}.svg"
            svg_path.write_text(svg, encoding="utf-8")
            rasterize_svg(svg, png_path)
            image_url = f"{PUBLIC_BASE}/media/{item_id}.png"
            print(f"Wrote media/{item_id}.png ({png_path.stat().st_size} bytes) "
                  f"+ media/{item_id}.svg ({len(svg)} chars)")
        except Exception as e:
            # Don't block the post if image generation fails.
            print(f"WARN: SVG generation failed, posting text-only: {e}",
                  file=sys.stderr)
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
    })
    # Cap queue at last 200 entries
    queue = queue[-200:]
    save_queue(queue)
    print(f"Appended id={item_id} title={title!r} image={'yes' if image_url else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
