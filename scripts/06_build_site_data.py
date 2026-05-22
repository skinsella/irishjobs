"""
Merge occupations.csv + scores.json into site/data.json — the bundle the
frontend reads. Mirrors build_site_data.py in karpathy/jobs. Works even
when scores.json is missing (exposure becomes null).

Usage:
    uv run python scripts/06_build_site_data.py
"""

import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSV_IN = REPO / "occupations.csv"
SCORES_IN = REPO / "scores.json"
OUT = REPO / "site" / "data.json"


def main() -> None:
    scores: dict[str, dict] = {}
    if SCORES_IN.exists():
        for s in json.loads(SCORES_IN.read_text()):
            scores[s["slug"]] = s

    with CSV_IN.open() as f:
        rows = list(csv.DictReader(f))

    data = []
    for row in rows:
        slug = row["slug"]
        score = scores.get(slug, {})
        data.append({
            "title": row["title"],
            "slug": slug,
            "category": row["category"],
            "pay": int(row["median_pay_annual"]) if row["median_pay_annual"] else None,
            "jobs": int(row["num_jobs_2024"]) if row["num_jobs_2024"] else None,
            "outlook": int(row["outlook_pct"]) if row["outlook_pct"] not in ("", None) else None,
            "outlook_desc": row["outlook_desc"],
            "education": row["entry_education"],
            "exposure": score.get("exposure"),
            "exposure_rationale": score.get("rationale"),
            "url": row.get("url", ""),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data))

    total_jobs = sum(d["jobs"] for d in data if d["jobs"])
    print(f"Wrote {len(data)} occupations to {OUT.relative_to(REPO)}")
    print(f"  Total employment represented: {total_jobs:,}")
    print(f"  With AI exposure score: {sum(1 for d in data if d['exposure'] is not None)}/{len(data)}")


if __name__ == "__main__":
    main()
