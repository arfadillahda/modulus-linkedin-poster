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
import json
import os
import pathlib
import random
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "personal_queue.json"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

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
    # Strip code fences if the model added them despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


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

    queue.append({
        "id": item_id,
        "ts": now,
        "topic": topic,
        "stage": stage,
        "title": title,
        "body": body,
    })
    # Cap queue at last 200 entries
    queue = queue[-200:]
    save_queue(queue)
    print(f"Appended id={item_id} title={title!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
