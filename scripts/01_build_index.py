"""
Parse the NSB 2025 Appendix to extract every occupational group and its
SOC2010 unit-group mapping. Mirrors the role of parse_occupations.py in
the US repo, but built off the PDF Appendix rather than an A-Z webpage.

Output: occupations.json — one entry per NSB occupational group with
title, slug, category (NSB sector chapter), soc_descriptions list, and
section anchor.

Usage:
    uv run python scripts/01_build_index.py
"""

import json
import re
from pathlib import Path

import pdfplumber
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _nsb_paths import latest_local_nsb

REPO = Path(__file__).resolve().parent.parent
PDF = latest_local_nsb()
OUT = REPO / "occupations.json"

APPENDIX_HEAD = "Breakdown of Occupational Groups"

# Sector names as they appear in the Appendix's leftmost column.
# (Slightly different from ToC names — e.g. "Sales & Customer Service" vs
# "Sales, Marketing & Customer Service Occupations" in the ToC.)
SECTOR_KEYWORDS = [
    "Science & Engineering",
    "ICT",
    "Business & Financial",
    "Healthcare",
    "Education",
    "Social & Care",
    "Legal & Security",
    "Construction",
    "Other Craft",
    "Agriculture & Animal Care",
    "Hospitality",
    "Arts, Sports & Tourism",
    "Transport & Logistics",
    "Administrative & Secretarial",
    "Sales & Customer Service",
    "Operatives & Elementary",
]


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[&,.]", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def find_appendix_pages(pdf: "pdfplumber.PDF") -> range:
    start = end = None
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if APPENDIX_HEAD in text and start is None:
            start = i
        if start is not None and "Email: slmru@solas.ie" in text:
            end = i
            break
    if start is None:
        raise RuntimeError(f"Could not find appendix heading {APPENDIX_HEAD!r}")
    if end is None:
        end = len(pdf.pages)
    return range(start, end)


def _norm(cell: str | None) -> str:
    if not cell:
        return ""
    return re.sub(r"\s+", " ", cell).strip()


def _clean_title(title: str) -> str:
    """Repair common PDF-extraction artefacts in group titles."""
    # PDF font kerning sometimes inserts a stray space mid-word
    # (e.g. "o peratives" → "operatives", "H airdressing" → "Hairdressing").
    title = re.sub(r"\b([a-zA-Z])\s+([a-z]{2,})\b", r"\1\2", title)
    # Stray period before "n.e.c.": "professionals. n.e.c." → "professionals n.e.c."
    title = re.sub(r"\.\s+(n\.e\.c\.)", r" \1", title)
    # Trailing comma / period oddities.
    title = re.sub(r"\s*,\s*$", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _match_sector(left_cell: str) -> str | None:
    """Match a leftmost-column cell value to one of our canonical sectors."""
    text = left_cell.lower()
    for sector in SECTOR_KEYWORDS:
        if sector.lower() in text:
            return sector
    return None


def parse_appendix(pdf: "pdfplumber.PDF", pages: range) -> list[dict]:
    """Walk the appendix table and emit one entry per occupational group.

    The appendix is a 3-column table:
      | Sector (left) | Group (middle) | SOC description (right) |

    Both sector and group are rowspan'd visually. pdfplumber's
    `find_tables().extract()` returns the sector value only on the row
    where it first appears, and otherwise leaves the cell blank — so we
    carry the running sector/group state forward.
    """
    current_sector: str | None = None
    current_group: str | None = None
    groups: dict[str, dict] = {}

    for page_idx in pages:
        page = pdf.pages[page_idx]
        for tbl in page.find_tables():
            data = tbl.extract()
            if not data or len(data[0]) < 3:
                continue
            for row in data:
                cells = [_norm(c) for c in row]
                if not cells:
                    continue
                left_cell = cells[0]
                middle = [c for c in cells[1:-1] if c]
                group_cell = " ".join(middle).strip()
                soc_cell = cells[-1]

                if soc_cell == "SOC Description":
                    continue

                if left_cell:
                    matched = _match_sector(left_cell)
                    if matched:
                        current_sector = matched

                if group_cell and not soc_cell:
                    # Continuation row of a multi-line group title.
                    if current_group and current_group in groups:
                        joined = f"{current_group} {group_cell}".strip()
                        joined = re.sub(r"\s+", " ", joined)
                        # Rename the dict key to preserve identity / order.
                        entry = groups.pop(current_group)
                        entry["title"] = joined
                        entry["slug"] = slugify(joined)
                        groups[joined] = entry
                        current_group = joined
                    else:
                        # Title started in this row before its first SOC appears.
                        current_group = (current_group or "") + " " + group_cell
                        current_group = re.sub(r"\s+", " ", current_group).strip()
                    continue
                elif group_cell:
                    current_group = group_cell

                if current_group and soc_cell:
                    entry = groups.get(current_group)
                    if entry is None:
                        entry = {
                            "title": current_group,
                            "slug": slugify(current_group),
                            "category": current_sector or "uncategorised",
                            "soc_descriptions": [],
                            "url": "",
                        }
                        groups[current_group] = entry
                    if soc_cell not in entry["soc_descriptions"]:
                        entry["soc_descriptions"].append(soc_cell)
                    if entry["category"] == "uncategorised" and current_sector:
                        entry["category"] = current_sector

    return list(groups.values())


def main() -> None:
    with pdfplumber.open(PDF) as pdf:
        pages = find_appendix_pages(pdf)
        print(f"Appendix pages: {pages.start + 1}..{pages.stop}")
        entries = parse_appendix(pdf, pages)

    NSB_URL = "https://www.solas.ie/research-lp/skills-labour-market-research-slmru/"
    for e in entries:
        e["title"] = _clean_title(e["title"])
        e["slug"] = slugify(e["title"])
        e["url"] = NSB_URL

    # Stable order: by category in NSB sector ordering, then by title.
    sector_order = {s: i for i, s in enumerate(SECTOR_KEYWORDS)}
    entries.sort(key=lambda x: (sector_order.get(x["category"], 99), x["title"]))

    OUT.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} occupational groups → {OUT.relative_to(REPO)}")

    from collections import Counter
    by_cat = Counter(e["category"] for e in entries)
    for sector in SECTOR_KEYWORDS:
        n = by_cat.get(sector, 0)
        print(f"  {n:3d}  {sector}")
    uncat = by_cat.get("uncategorised", 0)
    if uncat:
        print(f"  {uncat:3d}  ⚠ uncategorised")


if __name__ == "__main__":
    main()
