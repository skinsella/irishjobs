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

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _nsb_paths import latest_local_nsb_url, latest_local_nsb_year

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "occupations.json"
PAGES = REPO / "pages"
DEN11 = REPO / "raw" / "pxstat" / "DEN11.json"
EHQ15 = REPO / "raw" / "pxstat" / "EHQ15.json"
SECTION_PAGES = REPO / "raw" / "_nsb_section_pages.json"
OUT = REPO / "occupations.csv"

# Fallback landing page if the deep-link URL can't be constructed.
# Verified 2026-05-22: /research/ suffix returns 200, the bare /slmru/
# path returns 404 (which is what was shipping before).
SOLAS_LANDING_FALLBACK = (
    "https://www.solas.ie/research-lp/skills-labour-market-research-slmru/research/"
)

# Map NSB sector chapter → Department of Finance AI risk tier.
# Tiers follow the framework in Williamson, Gannon, Daly, Fitzgerald & Coates
# (2024) "Artificial Intelligence: Friend or Foe? A Review of How AI Could
# Impact Ireland's Labour Market" and the Department of Finance Economic
# Insights Volume 1 2026, which classifies sectors by their concentration of
# "at risk" occupations. The DoF analysis is at NACE-sector level; we map
# NSB occupational sectors to the closest analogue.
DOF_RISK_TIER = {
    "ICT":                              "high",   # ICT — DoF's named high-risk sector
    "Business & Financial":             "high",   # Financial activities — DoF high-risk
    "Administrative & Secretarial":     "high",   # Heavy substitutable component
    "Sales & Customer Service":         "high",   # Customer service highly digitised
    "Science & Engineering":            "medium",
    "Education":                        "medium",
    "Legal & Security":                 "medium",
    "Arts, Sports & Tourism":           "medium",
    "Healthcare":                       "low",    # Physical care, regulated
    "Social & Care":                    "low",    # Care work, in-person
    "Construction":                     "low",
    "Other Craft":                      "low",
    "Agriculture & Animal Care":        "low",
    "Hospitality":                      "low",
    "Transport & Logistics":            "low",
    "Operatives & Elementary":          "low",
}


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
    (["arts", "entertainment", "recreation",
      "other nace", "other service"], 12),                          # Arts/personal services (R,S)
]


# Maps the 21 NACE Rev.2 sections to the DEN11 13-section index used by
# NACE_KEYWORD_MAP. (DEN11 collapses K+L and R+S; B-E into "Industry".)
NACE_DIVISION_TO_DEN11_IDX = {
    # B-E Industry (DEN11 idx 0)
    **{d: 0 for d in [5,6,7,8,9, 10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33, 35, 36,37,38,39]},
    # F Construction (1)
    **{d: 1 for d in [41,42,43]},
    # G Wholesale and retail (2)
    **{d: 2 for d in [45,46,47]},
    # H Transportation and storage (3)
    **{d: 3 for d in [49,50,51,52,53]},
    # I Accommodation and food (4)
    **{d: 4 for d in [55,56]},
    # J Information & communication (ICT) (5)
    **{d: 5 for d in [58,59,60,61,62,63]},
    # K-L Financial/Insurance/Real estate (6)
    **{d: 6 for d in [64,65,66, 68]},
    # M Professional/scientific/technical (7)
    **{d: 7 for d in [69,70,71,72,73,74,75]},
    # N Administrative/support (8)
    **{d: 8 for d in [77,78,79,80,81,82]},
    # O Public admin/defence (9)
    **{d: 9 for d in [84]},
    # P Education (10)
    **{d: 10 for d in [85]},
    # Q Health/social (11)
    **{d: 11 for d in [86,87,88]},
    # R-S Arts/entertainment + other personal services (12)
    **{d: 12 for d in [90,91,92,93, 94,95,96]},
}


def _ehq15_label_to_divisions(label: str) -> list[int]:
    """Parse the (NN), (NN,MM), or (NN to MM) suffix off an EHQ15 label."""
    m = re.search(r"\(([0-9, to]+)\)\s*$", label)
    if not m:
        return []
    body = m.group(1).replace(" to ", "-")
    out: list[int] = []
    for chunk in re.split(r",\s*", body):
        chunk = chunk.strip()
        if "-" in chunk:
            a, b = chunk.split("-")
            try:
                out.extend(range(int(a), int(b) + 1))
            except ValueError:
                pass
        else:
            try:
                out.append(int(chunk))
            except ValueError:
                pass
    return out


def load_ehq15_mean_weekly_latest() -> tuple[dict[int, float], str]:
    """Compute mean weekly earnings by DEN11-style sector index from EHQ15,
    using the latest available quarter. Returns ({den11_idx: €/week}, "YYYYQn").

    EHQ15 is at 2-digit NACE division level. We group each division into
    its NACE Rev.2 section (e.g. all manufacturing divisions → Industry),
    average the per-division mean weekly earnings within each section,
    and return one number per DEN11 sector index.
    """
    d = json.loads(EHQ15.read_text())
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

    statistic_idx = label_idx(dim_ids[0], "Earnings Per Week")
    quarters = list(dims[dim_ids[1]]["category"]["label"].values())
    latest_q = quarters[-1]
    quarter_idx = len(quarters) - 1

    # Average division-level earnings within each DEN11 section.
    bucket: dict[int, list[float]] = {}
    sector_codes = dims[dim_ids[2]]["category"]["index"]
    sector_labels = dims[dim_ids[2]]["category"]["label"]
    for sec_idx, code in enumerate(sector_codes):
        label = sector_labels[code]
        divisions = _ehq15_label_to_divisions(label)
        if not divisions:
            continue
        # Map each division to a DEN11 section index; skip divisions we
        # don't classify (rare; "L Real estate" is folded into K).
        targets = {NACE_DIVISION_TO_DEN11_IDX.get(div)
                   for div in divisions
                   if NACE_DIVISION_TO_DEN11_IDX.get(div) is not None}
        flat = ((statistic_idx * sizes[1] + quarter_idx) * sizes[2]) + sec_idx
        try:
            v = values[flat]
        except IndexError:
            continue
        if v is None:
            continue
        for tgt in targets:
            bucket.setdefault(tgt, []).append(float(v))

    out = {idx: sum(vals)/len(vals) for idx, vals in bucket.items() if vals}
    return out, latest_q


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
    """Generate an outlook_desc string in the US OOH style.

    NSB shortage tags exist in the PDF but our 2-column-layout parser
    cannot extract them reliably (it has attributed e.g. carpenters'
    narrative text to plumbers). Until the per-occupation narrative
    parser is rewritten, we ignore the captured shortage value and
    derive outlook_desc purely from the growth percentage. Honest
    derived label > misattributed real label.
    """
    _ = shortage  # not used; see docstring
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


def build_url_resolver():
    """Return a function entry → URL that points into the NSB PDF at the
    occupation's Section 10 chapter when possible. Falls back to the SOLAS
    landing page (verified live)."""
    nsb_url = latest_local_nsb_url()
    section_pages: dict[str, int] = {}
    if SECTION_PAGES.exists():
        section_pages = json.loads(SECTION_PAGES.read_text())

    # Section names like "ICT Occupations" need to be matched to the
    # appendix-style category like "ICT" (which is what entries carry).
    # Build a {canonical-tokens: page} lookup.
    STOP = {"and", "the", "of", "in", "for", "marketing", "secretarial",
            "n", "e", "c"}

    def canon_tokens(s: str) -> frozenset[str]:
        s = re.sub(r"\s*Occupations(?:\s+n\.e\.c\.)?\s*$", "", s).strip()
        return frozenset(t for t in re.findall(r"\w+", s.lower()) if t not in STOP)

    tok_to_page = {canon_tokens(name): pg for name, pg in section_pages.items()}

    def resolve(entry: dict) -> str:
        if not nsb_url:
            return SOLAS_LANDING_FALLBACK
        want = canon_tokens(entry.get("category", ""))
        best, best_n = None, 0
        for keys, pg in tok_to_page.items():
            n = len(keys & want)
            if n > best_n:
                best_n, best = n, pg
        if best is not None:
            return f"{nsb_url}#page={best}"
        return nsb_url  # bare PDF link if no section match
    return resolve


def main() -> None:
    entries = json.loads(INDEX.read_text())
    # Pay axis: EHQ15 mean weekly earnings (latest available quarter,
    # currently Q3 2025) is preferred for currency; DEN11 median weekly
    # (2024 full year) is kept as a cross-reference.
    #
    # METHODOLOGY NOTE: EHQ15 reports MEAN weekly earnings (sensitive to
    # outliers) while DEN11 reports MEDIAN (insensitive). For most
    # sectors the mean exceeds the median by ~5–10% because of the
    # right-skewed pay distribution. The frontend labels the layer as
    # "Mean weekly earnings, Q3 2025" so the methodology is visible.
    weekly_by_sector, latest_q = load_ehq15_mean_weekly_latest()
    resolve_url = build_url_resolver()
    print(f"EHQ15 mean weekly earnings by NACE sector ({latest_q}):")
    for idx, val in sorted(weekly_by_sector.items()):
        print(f"  [{idx}] €{val:,.2f}")

    fieldnames = [
        "title", "category", "slug", "soc_code",
        "median_pay_annual", "median_pay_hourly",
        "entry_education", "work_experience", "training",
        "num_jobs_2024", "projected_employment_2034",
        "outlook_pct", "outlook_desc", "employment_change",
        "dof_risk_tier",
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
            "dof_risk_tier": DOF_RISK_TIER.get(entry["category"], ""),
            "url": resolve_url(entry),
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
