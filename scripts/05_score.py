"""
Score each occupation's AI exposure using an LLM via OpenRouter.

Lifted verbatim from karpathy/jobs `score.py`, with three changes:
  • Paths point at this project's pages/ and scores.json.
  • System prompt mentions SOLAS NSB instead of the US Bureau of
    Labor Statistics — same calibration anchors otherwise.
  • Reuses incremental caching: re-runs are idempotent.

Usage:
    uv run python scripts/05_score.py
    uv run python scripts/05_score.py --model google/gemini-3-flash-preview
    uv run python scripts/05_score.py --start 0 --end 10
"""

import argparse
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "occupations.json"
PAGES = REPO / "pages"
OUT = REPO / "scores.json"

DEFAULT_MODEL = "google/gemini-3-flash-preview"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """\
You are an expert analyst evaluating how exposed different occupations are to \
AI. You will be given a detailed description of an occupation from the SOLAS \
National Skills Bulletin (Ireland's annual labour-market report).

Rate the occupation on TWO independent 0–10 axes. This split follows the \
Department of Finance / DETE framework in Williamson, Gannon, Daly, \
Fitzgerald and Coates (2024), "Artificial Intelligence: Friend or Foe? \
A Review of How AI Could Impact Ireland's Labour Market", which distinguishes \
*complementary* exposure ("AI augments the worker") from *substitutable* \
exposure ("AI displaces the worker"). About 33% of Irish employment falls \
into each bucket; the same role can be high on both at once.

### Axis 1 — Complementary exposure (0–10)
How much does AI make a worker in this role *more productive* without \
displacing them? Examples of complementary use:
  • A software developer writes 2–3× more code with AI assistants
  • A doctor uses AI for differential diagnosis and report drafting
  • A teacher uses AI to generate lesson plans and personalised feedback
  • A research scientist uses AI to summarise literature and prototype models

Score high (7+) when the worker keeps full responsibility but their throughput, \
quality, or scope expands materially with AI tools. Score low (0–2) when the \
job has no information-processing component AI can plausibly speed up.

### Axis 2 — Substitutable exposure (0–10)
How much of the role's *core economic activity* could be done by AI alone, \
without a human in the loop? Examples of substitutable tasks:
  • Telemarketing scripts, first-line customer service triage
  • Routine document review, basic translation, copy-editing
  • Data entry, transcription, simple report generation
  • Basic image tagging, content moderation, FAQ chat

Score high (7+) when more than half of the role's billable hours could be \
replaced by current or near-future AI without serious quality loss. Score low \
(0–2) when the job requires physical presence, regulated human judgment, \
strong client relationships, or trust-bound human interaction.

### Calibration grid (anchor points)

| Occupation                  | Comp. | Subst. | Why                                    |
|-----------------------------|-------|--------|----------------------------------------|
| Software developer          | 9     | 4      | Massive productivity gain; AI can't yet own production systems end-to-end |
| Doctor / nurse              | 7     | 1      | AI augments diagnosis; physical/regulated tasks remain human |
| Teacher                     | 7     | 2      | Strong prep & feedback augmentation; classroom presence still human |
| Data entry clerk            | 3     | 10     | Almost no value to add by augmentation; fully substitutable |
| Telemarketer / call centre  | 4     | 9      | Modest scripting help; the actual calls are increasingly bot-handled |
| Paralegal / copywriter      | 7     | 7      | Both axes high: huge productivity boost AND large substitutable share |
| Graphic designer            | 7     | 6      | Major augmentation; substitutable on commodity work, not premium |
| Plumber / electrician       | 1     | 0      | Trivially low — neither augmentation nor substitution applies |
| Care worker / hairdresser   | 1     | 0      | Physical presence + trust; AI is irrelevant to the core job |
| Accountant                  | 7     | 6      | Reports, reconciliation; routine bookkeeping is substitutable |
| Lawyer (barrister/solicitor)| 7     | 4      | Drafting/research augmented; advocacy and client trust not |
| Police officer              | 4     | 1      | Some report-writing help; substantive role is human |

Respond with ONLY a JSON object in this exact format, no other text:
{
  "exposure_complementary": <0-10>,
  "exposure_substitutable": <0-10>,
  "rationale": "<2-3 sentences explaining where each axis sits and why>"
}\
"""


def score_occupation(client, text, model):
    response = client.post(
        API_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    # Tolerate trailing commas before close braces (common LLM JSON tic).
    import re as _re
    content = _re.sub(r",(\s*[}\]])", r"\1", content)
    return json.loads(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit(
            "OPENROUTER_API_KEY not set. Add it to .env or export it.\n"
            "Get a key at https://openrouter.ai/keys"
        )

    entries = json.loads(INDEX.read_text())
    subset = entries[args.start:args.end]

    scores: dict[str, dict] = {}
    if OUT.exists() and not args.force:
        for entry in json.loads(OUT.read_text()):
            scores[entry["slug"]] = entry

    print(f"Scoring {len(subset)} occupations with {args.model}")
    print(f"Already cached: {len(scores)}")

    errors = []
    with httpx.Client() as client:
        for i, occ in enumerate(subset):
            slug = occ["slug"]
            if slug in scores:
                continue
            md_path = PAGES / f"{slug}.md"
            if not md_path.exists():
                print(f"  [{i+1}] SKIP {slug} (no markdown)")
                continue
            text = md_path.read_text()
            print(f"  [{i+1}/{len(subset)}] {occ['title']}...", end=" ", flush=True)
            try:
                result = score_occupation(client, text, args.model)
                comp = int(result["exposure_complementary"])
                subst = int(result["exposure_substitutable"])
                # Backwards-compat single exposure score for the original colour
                # layer: the maximum of the two axes captures "how much will AI
                # reshape this role overall?" (either through augmentation OR
                # displacement).
                exposure = max(comp, subst)
                scores[slug] = {
                    "slug": slug,
                    "title": occ["title"],
                    "exposure": exposure,
                    "exposure_complementary": comp,
                    "exposure_substitutable": subst,
                    "rationale": result.get("rationale", ""),
                }
                print(f"comp={comp} subst={subst} (max={exposure})")
            except Exception as e:
                print(f"ERROR: {e}")
                errors.append(slug)
            OUT.write_text(json.dumps(list(scores.values()), indent=2))
            if i < len(subset) - 1:
                time.sleep(args.delay)

    print(f"\nDone. Scored {len(scores)} occupations, {len(errors)} errors.")
    if errors:
        print(f"Errors: {errors}")

    vals = [s for s in scores.values() if "exposure" in s]
    if vals:
        for axis in ("exposure_complementary", "exposure_substitutable", "exposure"):
            if not all(axis in s for s in vals):
                continue
            avg = sum(s[axis] for s in vals) / len(vals)
            by_score: dict[int, int] = {}
            for s in vals:
                by_score[s[axis]] = by_score.get(s[axis], 0) + 1
            label = {
                "exposure_complementary": "Complementary (augments)",
                "exposure_substitutable": "Substitutable (displaces)",
                "exposure": "Overall (max of two)",
            }[axis]
            print(f"\n{label}: average {avg:.1f}")
            for k in sorted(by_score):
                bar = "█" * by_score[k]
                print(f"  {k}: {bar} ({by_score[k]})")


if __name__ == "__main__":
    main()
