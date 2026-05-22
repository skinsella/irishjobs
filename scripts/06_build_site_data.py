"""
Merge occupations.csv + scores.json into site/data.json — the bundle the
frontend reads. Mirrors build_site_data.py in karpathy/jobs. Works even
when scores.json is missing (exposure becomes null).

Also emits a `vintage` block recording which year/quarter of each source
the data came from, so the frontend can show data-vintage badges per
layer without hard-coding strings.

Usage:
    uv run python scripts/06_build_site_data.py
"""

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSV_IN = REPO / "occupations.csv"
SCORES_IN = REPO / "scores.json"
OUT = REPO / "site" / "data.json"
PXSTAT_DIR = REPO / "raw" / "pxstat"

sys.path.insert(0, str(REPO / "scripts"))
from _nsb_paths import latest_local_nsb_year


def _latest_label_in_pxstat(table_code: str, dim_key: str) -> str | None:
    """Pull the last category label for a dimension in a cached PxStat JSON."""
    f = PXSTAT_DIR / f"{table_code}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    dims = d.get("dimension", {})
    if dim_key not in dims:
        return None
    labels = list(dims[dim_key].get("category", {}).get("label", {}).values())
    return labels[-1] if labels else None


def build_vintage_block() -> dict:
    """Return a dict describing the vintage of every layer the site shows."""
    nsb_year = latest_local_nsb_year()
    # The NSB-YYYY edition reports YYYY-1 annual averages and growth
    # over the prior five years (e.g. NSB 2025 → 2024 annual data and
    # 2019-2024 5-yr growth).
    data_year = nsb_year - 1
    growth_window = f"{data_year - 5}–{data_year}"

    den11_year = _latest_label_in_pxstat("DEN11", "TLIST(A1)")
    return {
        "jobs": {
            "label": f"NSB {nsb_year}",
            "detail": f"Annual average {data_year}",
            "source": "SOLAS National Skills Bulletin",
        },
        "outlook": {
            "label": f"NSB {nsb_year}",
            "detail": f"5-yr growth {growth_window}",
            "source": "SOLAS National Skills Bulletin",
        },
        "pay": {
            "label": f"CSO DEN11 {den11_year}" if den11_year else "CSO DEN11",
            "detail": f"Median weekly earnings × NACE-sector mix × 52",
            "source": "CSO Earnings Analysis Admin Data, sector-weighted",
        },
        "education": {
            "label": f"NSB {nsb_year}",
            "detail": "%3rd-level → NFQ-tier classification (40/100 coverage)",
            "source": "SOLAS National Skills Bulletin",
        },
        "exposure_complementary": {
            "label": "LLM",
            "detail": "Gemini Flash via OpenRouter, Friend-or-Foe rubric",
            "source": "Model estimate (not measured data)",
        },
        "exposure_substitutable": {
            "label": "LLM",
            "detail": "Gemini Flash via OpenRouter, Friend-or-Foe rubric",
            "source": "Model estimate (not measured data)",
        },
        "exposure": {
            "label": "LLM",
            "detail": "max(complementary, substitutable)",
            "source": "Derived from model estimates",
        },
        "dof_risk_tier": {
            "label": "DoF 2024 + manual",
            "detail": "Hand-mapped from NSB sector → DoF NACE-sector tier",
            "source": "Williamson et al. (2024) framework",
        },
    }


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
            "exposure_complementary": score.get("exposure_complementary"),
            "exposure_substitutable": score.get("exposure_substitutable"),
            "exposure_rationale": score.get("rationale"),
            "dof_risk_tier": row.get("dof_risk_tier", "") or None,
            "url": row.get("url", ""),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Wrap rows + vintage block in a top-level object. The frontend
    # checks for both shapes (legacy list, or {rows, vintage}) so older
    # cached HTML can still load.
    bundle = {"rows": data, "vintage": build_vintage_block()}
    OUT.write_text(json.dumps(bundle))

    total_jobs = sum(d["jobs"] for d in data if d["jobs"])
    print(f"Wrote {len(data)} occupations to {OUT.relative_to(REPO)}")
    print(f"  Total employment represented: {total_jobs:,}")
    print(f"  With AI exposure score: {sum(1 for d in data if d['exposure'] is not None)}/{len(data)}")
    print(f"  Vintage block:")
    for layer, info in bundle["vintage"].items():
        print(f"    {layer:<28} {info['label']:<24} {info['detail']}")


if __name__ == "__main__":
    main()
