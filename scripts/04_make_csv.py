"""
Build occupations.csv from the parsed NSB profiles (pages/*.md) and the
CSO sector-earnings cache (raw/pxstat/DEN11.json). Mirrors make_csv.py
in the US repo; column names are kept identical so the frontend can be
ported with minimal edits.

Pay strategy (Ireland): the CSO does not publish median earnings by
SOC2010, so we compute a sector-weighted estimate using the NSB
profile's "Main NACE sectors of employment" mix multiplied by DEN11's
median weekly earnings per sector. Annual = weekly × 52, hourly ÷ 39.

Education strategy: NSB's per-group "% Third-level graduates" field is
mapped onto the eight US OOH education tiers using the bands below,
so the existing frontend education colour scale works unchanged.

Outlook: 5-yr historical employment growth (2019–2024) from the NSB.
The frontend label needs to read "5-yr historical change", not
"BLS 10-yr projection".

Usage:
    uv run python scripts/04_make_csv.py
"""

import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "occupations.json"
PAGES = REPO / "pages"
DEN11 = REPO / "raw" / "pxstat" / "DEN11.json"
OUT = REPO / "occupations.csv"

# Map NSB NACE-sector phrases → CSO DEN11 sector indices.
# NSB uses short names ("ICT", "Industry", "Professional activities");
# DEN11 uses long-form labels. We match by representative keyword.
NACE_KEYWORD_MAP = [
    (["industry", "industrial"], 0),                                # Industry (B-E)
    (["construction"], 1),                                          # Construction (F)
    (["wholesale", "retail"], 2),                                   # Wholesale and retail (G)
    (["transport", "storage", "logistics"], 3),                     # Transportation and storage (H)
    (["accommodation", "food service", "hospitality"], 4),          # Accommodation and food (I)
    (["ict", "information and communication"], 5),                  # ICT (J)
    (["financial", "insurance", "real estate"], 6),                 # Fin/Ins/RE (K,L)
    (["professional activities", "scientific", "technical"], 7),    # Prof/sci/tech (M)
    (["administrative", "support service"], 8),                     # Admin/support (N)
    (["public administration", "defence"], 9),                      # Public admin (O)
    (["education"], 10),                                            # Education (P)
    (["health", "social work"], 11),                                # Health/social (Q)
    (["arts", "entertainment", "recreation"], 12),                  # Arts/entertain (R,S)
]


def load_den11_median_weekly_2024() -> dict[int, float]:
    """Load DEN11 → dict {sector_idx: median weekly earnings €} for 2024
    (All nationalities). PxStat ships JSON-stat with list-shaped indices."""
    d = json.loads(DEN11.read_text())
    dims = d["dimension"]
    dim_ids = d["id"]
    sizes = d["size"]
    values = d["value"]

    def label_idx(dim_id: str, label: str) -> int:
        cat = dims[dim_id]["category"]
        for code, name in cat["label"].items():
            if name == label:
                return cat["index"].index(code)
        raise KeyError(f"{label!r} not in {dim_id}")

    statistic_idx = label_idx(dim_ids[0], "Median Weekly Earnings")
    year_idx = label_idx(dim_ids[1], "2024")
    nat_idx = label_idx(dim_ids[3], "All nationalities")

    out: dict[int, float] = {}
    sector_dim = dim_ids[2]
    sector_codes = dims[sector_dim]["category"]["index"]
    for sector_idx, _code in enumerate(sector_codes):
        flat = (
            ((statistic_idx * sizes[1] + year_idx) * sizes[2] + sector_idx)
            * sizes[3] + nat_idx
        )
        v = values[flat]
        if v is not None:
            out[sector_idx] = float(v)
    return out


def match_nace(name: str) -> int | None:
    n = name.lower()
    for keywords, idx in NACE_KEYWORD_MAP:
        if any(k in n for k in keywords):
            return idx
    return None


def parse_md_field(md: str, label: str) -> str | None:
    """Pull a row value from the Quick Facts markdown table."""
    pattern = rf"^\|\s*{re.escape(label)}\s*\|\s*([^|]+?)\s*\|$"
    m = re.search(pattern, md, re.MULTILINE)
    return m.group(1).strip() if m else None


def parse_nace_block(md: str) -> list[tuple[float, str]]:
    """Extract the 'Top NACE economic sectors of employment' bullet list."""
    block_m = re.search(
        r"\*\*Top NACE economic sectors of employment:\*\*\s*\n((?:\s*-\s*[\[\]\d%]+ .+\n?)+)",
        md,
    )
    out: list[tuple[float, str]] = []
    if not block_m:
        return out
    for line in block_m.group(1).splitlines():
        m = re.match(r"\s*-\s*(\[?\d+%?\]?)\s+(.+)", line)
        if m:
            pct_raw = m.group(1).strip("[]%")
            try:
                pct = float(pct_raw)
            except ValueError:
                continue
            out.append((pct, m.group(2).strip()))
    return out


# Map %Third-level to the same eight education tiers the US frontend uses.
EDU_THRESHOLDS = [
    (90, "Doctoral or professional degree"),
    (80, "Master's degree"),
    (60, "Bachelor's degree"),
    (45, "Associate's degree"),
    (30, "Some college, no degree"),
    (15, "Postsecondary nondegree award"),
    (5,  "High school diploma or equivalent"),
    (0,  "No formal educational credential"),
]


def map_education(pct_third_level: float | None, sector: str) -> str:
    """Approximate the modal entry-level education from %3rd-level.

    These thresholds are calibrated against typical NSB profiles:
    >90% — almost universally degree-required (e.g. doctors, lawyers)
    80-90% — masters-track professional (e.g. social workers, teachers)
    60-80% — degree expected (most professional occupations)
    45-60% — degree common, not required
    30-45% — some post-secondary
    15-30% — post-secondary nondegree (e.g. apprenticeships)
    5-15%  — secondary school
    <5%    — no formal credential
    """
    if pct_third_level is None:
        return ""
    for threshold, label in EDU_THRESHOLDS:
        if pct_third_level >= threshold:
            return label
    return "No formal educational credential"


def classify_outlook(growth_pct: float | None, shortage: str) -> str:
    """Generate an outlook_desc string in the US OOH style."""
    if shortage:
        # The NSB's verbal tag is more informative than a percentage band.
        return f"{shortage}"
    if growth_pct is None:
        return ""
    if growth_pct >= 5:
        return "Much faster than average"
    if growth_pct >= 3:
        return "Faster than average"
    if growth_pct >= 1:
        return "As fast as average"
    if growth_pct >= 0:
        return "Slower than average"
    return "Decline"


def main() -> None:
    entries = json.loads(INDEX.read_text())
    weekly_by_sector = load_den11_median_weekly_2024()
    print(f"DEN11 median weekly earnings by NACE sector (2024):")
    for idx, val in sorted(weekly_by_sector.items()):
        print(f"  [{idx}] €{val:,.2f}")

    fieldnames = [
        "title", "category", "slug", "soc_code",
        "median_pay_annual", "median_pay_hourly",
        "entry_education", "work_experience", "training",
        "num_jobs_2024", "projected_employment_2034",
        "outlook_pct", "outlook_desc", "employment_change",
        "url",
    ]

    rows = []
    for entry in entries:
        slug = entry["slug"]
        md_path = PAGES / f"{slug}.md"
        if not md_path.exists():
            continue
        md = md_path.read_text()

        # Parse stats out of the MD quick-facts table.
        emp = parse_md_field(md, "Persons in employment (2024 annual avg)")
        emp_val = int(emp.replace(",", "")) if emp else None
        growth = parse_md_field(md, "Annual average growth 2019–2024")
        growth_val = (
            float(growth.rstrip("%").replace("+", ""))
            if growth else None
        )
        pct_3l = parse_md_field(md, "% Third-level graduates")
        pct_3l_val = float(pct_3l.rstrip("%")) if pct_3l else None
        shortage = parse_md_field(md, "Skills shortage assessment") or ""

        # Sector-weighted median weekly earnings.
        nace_mix = parse_nace_block(md)
        wW = wT = 0.0
        for pct, name in nace_mix:
            sidx = match_nace(name)
            if sidx is None or sidx not in weekly_by_sector:
                continue
            wW += pct * weekly_by_sector[sidx]
            wT += pct
        median_weekly = (wW / wT) if wT > 0 else None
        annual = round(median_weekly * 52) if median_weekly else None
        hourly = round(median_weekly / 39, 2) if median_weekly else None  # IE full-time avg ~39h

        row = {
            "title": entry["title"],
            "category": entry["category"],
            "slug": slug,
            "soc_code": "; ".join(entry.get("soc_descriptions", [])[:3]),
            "median_pay_annual": annual or "",
            "median_pay_hourly": hourly or "",
            "entry_education": map_education(pct_3l_val, entry["category"]),
            "work_experience": "",
            "training": "",
            "num_jobs_2024": emp_val or "",
            "projected_employment_2034": "",
            "outlook_pct": (round(growth_val) if growth_val is not None else ""),
            "outlook_desc": classify_outlook(growth_val, shortage),
            "employment_change": "",
            "url": entry["url"],
        }
        rows.append(row)

    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUT.relative_to(REPO)}")

    n_emp = sum(1 for r in rows if r["num_jobs_2024"])
    n_pay = sum(1 for r in rows if r["median_pay_annual"])
    n_edu = sum(1 for r in rows if r["entry_education"])
    n_out = sum(1 for r in rows if r["outlook_pct"] != "")
    print(f"  with employment count:  {n_emp}/{len(rows)}")
    print(f"  with pay estimate:      {n_pay}/{len(rows)}")
    print(f"  with education tier:    {n_edu}/{len(rows)}")
    print(f"  with outlook %:         {n_out}/{len(rows)}")

    total_jobs = sum(int(r["num_jobs_2024"]) for r in rows if r["num_jobs_2024"])
    print(f"  total employment represented: {total_jobs:,}")


if __name__ == "__main__":
    main()
