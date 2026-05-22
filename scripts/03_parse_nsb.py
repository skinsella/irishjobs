"""
Parse NSB 2025 Section 10 profiles into per-occupation Markdown files.

For each occupational group in occupations.json this script writes
pages/<slug>.md, formatted to look like the US OOH per-occupation page:
  • Quick Facts table (employment, growth, %female, %FT, %55+, %Irish,
    %3rd-level, employment permits, shortage tag)
  • Sector context (overall employment, share of total workforce, top NACE
    sectors)
  • Overall outlook narrative
  • Per-occupation narrative paragraph + skills-shortage tag

The MD is what the LLM scorer sees in step 5, so it should read like the
input the original rubric was calibrated on.

Usage:
    uv run python scripts/03_parse_nsb.py
    uv run python scripts/03_parse_nsb.py --force
"""

import argparse
import json
import re
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parent.parent
PDF = REPO / "raw" / "nsb_2025.pdf"
INDEX = REPO / "occupations.json"
OUT_DIR = REPO / "pages"

# Regex matching the "10.X Sector Occupations [n.e.c.]" headings.
SECTION_HEADER_RE = re.compile(
    r"^\s*(10\.(?:1[0-6]|[1-9]))\s+(.+?)\s*$", re.MULTILINE
)


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[&,.]", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def discover_sections(pdf: "pdfplumber.PDF") -> list[dict]:
    """Find every Section 10.X chapter heading and its page range."""
    found: list[tuple[int, str, str]] = []
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        for line in text.split("\n"):
            m = re.match(r"^(10\.(?:1[0-6]|[1-9]))\s+(.+?Occupations(?:\s+n\.e\.c\.)?)\s*$", line)
            if m:
                found.append((i, m.group(1).strip(), m.group(2).strip()))
                break  # one section start per page max
    # Resolve page ranges.
    sections: list[dict] = []
    for idx, (page_idx, num, name) in enumerate(found):
        end = found[idx + 1][0] if idx + 1 < len(found) else None
        sections.append({"num": num, "name": name, "start": page_idx, "end": end})
    return sections


def extract_section_text(pdf: "pdfplumber.PDF", section: dict) -> str:
    end = section["end"] if section["end"] is not None else len(pdf.pages)
    parts = []
    for i in range(section["start"], end):
        parts.append(pdf.pages[i].extract_text() or "")
    return "\n".join(parts)


def extract_figure_block(text: str) -> dict:
    """Pull the headline figure: per-group employment + growth, plus sector totals.

    The employed/growth lists are arrays in figure-column order; the
    column→group mapping is added by extract_figure_columns() below.
    """
    out: dict = {}
    employed_m = re.search(r"^Employed\s+([\d,\.\s\-\[\]]+)$", text, re.MULTILINE)
    growth_m = re.search(r"^Growth rate\s+([\d,\.\s\%\-\[\]]+)$", text, re.MULTILINE)
    overall_m = re.search(r"Overall employment\s+([\d,]+)", text)
    share_m = re.search(r"Share of total workforce\s+([\d\.]+%)", text)
    five_yr_m = re.search(r"\+?([\d,]+)\s+between 2019 and 2024", text)
    avg_yr_m = re.search(r"\+?([\d\.\-]+)%\s+on average annually", text)

    def _clean_num(s: str) -> str:
        return s.replace(",", "").replace("[", "").replace("]", "").strip()
    if employed_m:
        out["employed"] = [
            int(_clean_num(x)) for x in employed_m.group(1).split()
            if _clean_num(x).lstrip("-").isdigit()
        ]
    if growth_m:
        out["growth_pct"] = [
            float(_clean_num(x).rstrip("%"))
            for x in growth_m.group(1).split()
            if re.match(r"^\[?-?[\d\.]+%\]?$", x)
        ]
    if overall_m:
        out["sector_employment"] = int(overall_m.group(1).replace(",", ""))
    if share_m:
        out["sector_share"] = share_m.group(1)
    if five_yr_m:
        out["five_year_change"] = int(five_yr_m.group(1).replace(",", ""))
    if avg_yr_m:
        out["avg_annual_growth_pct"] = float(avg_yr_m.group(1))

    sectors = re.findall(
        r"(\[?\d+%\]?)\s*-\s*([A-Za-z &/,'\.]+?)(?=\s+(?:Main sectors|Employment growth|\+|\d+%|\Z))",
        text,
    )
    if sectors:
        out["main_nace_sectors"] = [(pct, name.strip().rstrip(",.")) for pct, name in sectors[:5]]
    return out


def extract_figure_columns(pdf: "pdfplumber.PDF", section: dict) -> list[str]:
    """Read the bar-chart x-axis labels from the section's first page.

    Strategy: find the words on the line containing "Employed" — their
    x-positions are the column anchors. Then find words ABOVE that line
    on the page (the x-axis labels of the figure) and bucket each word
    into the nearest column anchor. Cells are reconstructed by joining
    words in the same x-bucket top-to-bottom.
    """
    page = pdf.pages[section["start"]]
    words = page.extract_words(use_text_flow=False)
    # Find the "Employed" word and its row.
    employed = next((w for w in words if w["text"] == "Employed"), None)
    if not employed:
        return []
    row_y0, row_y1 = employed["top"], employed["bottom"]
    # The numbers on the same row as "Employed" — their x-centres are our
    # column anchors.
    same_row = [w for w in words
                if abs(w["top"] - row_y0) < 4 and w["text"] != "Employed"]
    same_row.sort(key=lambda w: w["x0"])
    anchors = [(w["x0"] + w["x1"]) / 2 for w in same_row]
    if not anchors:
        return []

    # Look at words ABOVE the Employed row (and below the chart's y-axis labels
    # which are short numbers/percentages).  The label band runs from about
    # row_y0 - 60 to row_y0 - 4 (~3 text lines).
    label_top = row_y0 - 80
    label_bot = row_y0 - 2
    label_words = [
        w for w in words
        if label_top < w["top"] < label_bot and w["x0"] > 70  # skip y-axis pct
        and not re.fullmatch(r"-|\d+(?:,\d+)*|\d+%", w["text"])
    ]
    # Bucket into the nearest anchor.
    buckets: dict[int, list] = {i: [] for i in range(len(anchors))}
    for w in label_words:
        cx = (w["x0"] + w["x1"]) / 2
        best_i = min(range(len(anchors)), key=lambda i: abs(anchors[i] - cx))
        buckets[best_i].append(w)
    labels: list[str] = []
    for i in range(len(anchors)):
        ws = sorted(buckets[i], key=lambda w: (w["top"], w["x0"]))
        # Group by vertical line, then join lines with a space.
        lines: list[list[str]] = []
        current_line: list[str] = []
        cur_y: float | None = None
        for w in ws:
            if cur_y is None or abs(w["top"] - cur_y) < 4:
                current_line.append(w["text"])
                cur_y = w["top"] if cur_y is None else cur_y
            else:
                lines.append(current_line)
                current_line = [w["text"]]
                cur_y = w["top"]
        if current_line:
            lines.append(current_line)
        label = " ".join(" ".join(line) for line in lines).strip()
        # Strip leaked right-axis percentage labels (e.g. "-4% -6% Foo" → "Foo").
        label = re.sub(r"^(?:-?\d+%\s+)+", "", label).strip()
        labels.append(label)
    return labels


def extract_group_table(pdf: "pdfplumber.PDF", section: dict) -> list[dict]:
    """Extract the per-group indicator table at the top of a section.

    Columns (after the row header): %Female, %FT, %55+, %Irish, %3rd-level,
    Employment permits, Recruitment Agency Survey tick.
    """
    rows: list[dict] = []
    end = section["end"] if section["end"] is not None else len(pdf.pages)
    for i in range(section["start"], min(section["start"] + 2, end)):
        page = pdf.pages[i]
        for tbl in page.find_tables():
            data = tbl.extract()
            if not data or len(data[0]) < 5:
                continue
            # Heuristic: a row with 6-8 cells where columns 2..6 are percents
            # or "..." is the per-group indicator row.
            for row in data:
                cells = [(c or "").replace("\n", " ").strip() for c in row]
                if len(cells) < 6:
                    continue
                name = cells[0]
                pcts = cells[1:6]
                if not name or name.startswith("%") or "Overall total" in name:
                    if "Overall total" in name:
                        rows.append({"name": "Overall total", "raw_cells": cells})
                    continue
                # Validate that the next 5 cells look like percents or dots.
                valid = sum(
                    1 for c in pcts if re.match(r"^\[?\d+%\]?$", c) or c in ("...", "…")
                )
                if valid >= 3:
                    rows.append({"name": name, "raw_cells": cells})
    return rows


def extract_group_narratives(text: str, group_titles: list[str]) -> dict[str, dict]:
    """For each group title, grab its dedicated paragraph + shortage tag.

    The NSB profile section after the headline figure consists of a series
    of paragraphs, each headed by the group's name (often broken across
    multiple lines in the PDF) and terminated by a "Shortage: <tag>" or
    "Skills shortage: <tag>" sentinel.
    """
    out: dict[str, dict] = {}
    # Normalise text to single spaces between line breaks for matching.
    flat = re.sub(r"[ \t]+", " ", text)
    flat = re.sub(r" *\n+ *", "\n", flat).strip()

    for g in group_titles:
        # Match group name (allow newlines between words) followed by a
        # paragraph that ends at the next group title or the next section.
        pattern_name = r"\s+".join(re.escape(w) for w in g.split())
        # Search for the title appearing as a standalone block (preceded by
        # newline) — this avoids matching mentions of the group inside other
        # paragraphs.
        m = re.search(rf"(?:^|\n){pattern_name}\s*\n(.+?)(?=\n(?:Shortage|Skills shortage):|\Z)",
                       flat, re.DOTALL | re.IGNORECASE)
        narrative = ""
        shortage = ""
        if m:
            narrative = m.group(1).strip()
            tail = flat[m.end(1):]
            tail_m = re.match(r"\n(Skills shortage|Shortage):\s*([^\n]+)", tail)
            if tail_m:
                shortage = tail_m.group(2).strip()
        out[g] = {"narrative": narrative, "shortage": shortage}
    return out


def stats_from_row(cells: list[str]) -> dict:
    """Pull %female, %FT, %55+, %Irish, %3rd, permits, RAS tick from a row."""
    def pct(s: str) -> float | None:
        s = s.replace("[", "").replace("]", "").strip()
        if s in ("...", "…", ""):
            return None
        m = re.match(r"^(-?\d+(?:\.\d+)?)%?$", s)
        return float(m.group(1)) if m else None

    out: dict = {}
    if len(cells) < 7:
        return out
    out["pct_female"] = pct(cells[1])
    out["pct_full_time"] = pct(cells[2])
    out["pct_55_plus"] = pct(cells[3])
    out["pct_irish"] = pct(cells[4])
    out["pct_third_level"] = pct(cells[5])
    # Employment permits cell sometimes has commas, sometimes empty.
    permits = re.sub(r"[^\d]", "", cells[6])
    out["new_permits"] = int(permits) if permits else None
    if len(cells) > 7 and "✓" in cells[7]:
        out["ras_flag"] = True
    return out


def render_md(entry: dict, group_stats: dict, sector_meta: dict,
              narrative: dict, sector_outlook: str) -> str:
    md: list[str] = []
    md.append(f"# {entry['title']}")
    md.append("")
    md.append(f"**Source:** SOLAS National Skills Bulletin 2025, "
              f"{sector_meta['num']} {sector_meta['name']}")
    md.append("")

    # Quick Facts
    md.append("## Quick Facts")
    md.append("")
    md.append("| Field | Value |")
    md.append("|-------|-------|")
    if group_stats.get("employed") is not None:
        md.append(f"| Persons in employment (2024 annual avg) | "
                  f"{group_stats['employed']:,} |")
    if group_stats.get("growth_pct") is not None:
        md.append(f"| Annual average growth 2019–2024 | "
                  f"{group_stats['growth_pct']:.1f}% |")
    for key, label in [
        ("pct_female", "% Female"),
        ("pct_full_time", "% Full-time"),
        ("pct_55_plus", "% Aged 55+"),
        ("pct_irish", "% Irish citizens"),
        ("pct_third_level", "% Third-level graduates"),
    ]:
        v = group_stats.get(key)
        if v is not None:
            md.append(f"| {label} | {v:.0f}% |")
    if group_stats.get("new_permits"):
        md.append(f"| New employment permits (2024) | "
                  f"{group_stats['new_permits']:,} |")
    if group_stats.get("ras_flag"):
        md.append("| Flagged by Recruitment Agency Survey | Yes |")
    if narrative.get("shortage"):
        md.append(f"| Skills shortage assessment | {narrative['shortage']} |")
    md.append(f"| Linked SOC2010 unit groups | "
              f"{len(entry.get('soc_descriptions', []))} |")
    md.append("")

    # SOC mapping
    if entry.get("soc_descriptions"):
        md.append("## SOC2010 unit groups included")
        md.append("")
        for soc in entry["soc_descriptions"]:
            md.append(f"- {soc}")
        md.append("")

    # Sector context
    md.append(f"## Sector context: {sector_meta['name']}")
    md.append("")
    if sector_meta.get("sector_employment"):
        md.append(f"- **Overall sector employment (2024):** "
                  f"{sector_meta['sector_employment']:,}")
    if sector_meta.get("sector_share"):
        md.append(f"- **Share of total workforce:** {sector_meta['sector_share']}")
    if sector_meta.get("avg_annual_growth_pct") is not None:
        md.append(f"- **Sector 5-yr avg annual growth:** "
                  f"{sector_meta['avg_annual_growth_pct']:+.1f}% "
                  f"(vs +3.4% for total workforce)")
    if sector_meta.get("main_nace_sectors"):
        md.append("- **Top NACE economic sectors of employment:**")
        for pct, name in sector_meta["main_nace_sectors"]:
            md.append(f"  - {pct} {name}")
    md.append("")

    if sector_outlook:
        md.append("## Overall outlook for this sector")
        md.append("")
        md.append(sector_outlook)
        md.append("")

    if narrative.get("narrative"):
        md.append("## Occupation-level outlook")
        md.append("")
        md.append(narrative["narrative"])
        md.append("")
        if narrative.get("shortage"):
            md.append(f"**Skills shortage:** {narrative['shortage']}")
            md.append("")

    return "\n".join(md)


def section_outlook_block(text: str) -> str:
    """Pull the 'Overall Outlook for these Occupations' paragraph(s)."""
    m = re.search(
        r"Overall Outlook for these Occupations\s*\n(.+?)(?=\n[A-Z][a-z]+,?\s*\n[A-Z]|\nShortage:|\Z)",
        text, re.DOTALL,
    )
    if not m:
        return ""
    body = m.group(1).strip()
    # Trim at first place where per-group narratives start (usually the
    # first group title appears as a multi-line phrase). We just keep the
    # first 2-3 paragraphs.
    paras = re.split(r"\n\s*\n", body)
    return "\n\n".join(paras[:3]).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-write even if pages/<slug>.md exists")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = json.loads(INDEX.read_text())
    by_slug = {e["slug"]: e for e in entries}

    with pdfplumber.open(PDF) as pdf:
        sections = discover_sections(pdf)
        print(f"Found {len(sections)} Section-10 sub-chapters")

        # For each section, parse stats + narratives, then write MD for
        # every group whose slug exists in occupations.json AND whose
        # name maps into the section.
        section_index_by_name = {}
        for s in sections:
            text = extract_section_text(pdf, s)
            figure = extract_figure_block(text)
            figure["columns"] = extract_figure_columns(pdf, s)
            rows = extract_group_table(pdf, s)
            outlook = section_outlook_block(text)
            # Pre-compute the indicator-row → figure-column mapping using
            # the more verbose indicator row names (which include words
            # like "Childminders" unabbreviated, unlike the figure labels).
            row_to_col: dict[int, int] = {}
            cols = figure["columns"]
            for ri, r in enumerate(rows):
                if r.get("name") == "Overall total":
                    continue
                row_tokens = set(re.findall(r"\w+", r["name"].lower())) - {
                    "and", "the", "of", "in", "for", "etc", "n", "e", "c"
                }
                best, best_score = None, 0
                for ci, lab in enumerate(cols):
                    if not lab:
                        continue
                    col_tokens = set(re.findall(r"\w+", lab.lower())) - {
                        "and", "the", "of", "in", "for", "etc", "n", "e", "c"
                    }
                    score = len(row_tokens & col_tokens)
                    # Add a stem-based bonus for short fragments
                    # (e.g. "Account" inside "Accountants").
                    for rtok in row_tokens:
                        for ctok in col_tokens:
                            if len(rtok) >= 4 and (rtok.startswith(ctok) or ctok.startswith(rtok)):
                                score += 0.5
                    if score > best_score:
                        best_score = score
                        best = ci
                if best is not None and best_score >= 1:
                    row_to_col[ri] = best
            figure["row_to_col"] = row_to_col
            section_index_by_name[s["name"]] = {
                "section": s,
                "figure": figure,
                "rows": rows,
                "outlook": outlook,
                "text": text,
            }

        # Build a fuzzy match between NSB section name and occupations.json category.
        # Appendix names: "Sales & Customer Service"; Section names:
        # "Sales, Marketing & Customer Service Occupations". Canonicalise to
        # a stable token set.
        def canon(name: str) -> frozenset[str]:
            x = re.sub(r"\s*Occupations(?:\s+n\.e\.c\.)?\s*$", "", name).strip()
            tokens = re.findall(r"\w+", x.lower())
            return frozenset(t for t in tokens if t not in
                             ("and", "the", "of", "in", "for", "marketing", "secretarial"))

        canon_to_section = {canon(name): info for name, info in section_index_by_name.items()}
        # Fallback resolution: pick the section with largest token overlap.
        def find_section(cat: str):
            want = canon(cat)
            best, best_n = None, 0
            for keys, info in canon_to_section.items():
                n = len(keys & want)
                if n > best_n:
                    best_n, best = n, info
            return best

        # ── One-to-one entry → figure-column assignment per section ──
        # Without this constraint, the fuzzy token matcher can map two or
        # more distinct occupational groups to the same chart column, which
        # caused massive sector inflation (Sales & Customer Service: +144%,
        # 1.04M jobs duplicated across the whole pipeline).
        #
        # We solve the assignment as a greedy bipartite matching: for each
        # section, compute the pairwise (entry, column) match score, then
        # repeatedly take the highest-scoring pair, lock both sides, and
        # repeat until no positive-score pair remains.
        STOPWORDS = {"and", "the", "of", "in", "for", "etc", "n", "e", "c", "&"}

        def tokens(s: str) -> set[str]:
            return {t for t in re.findall(r"\w+", s.lower()) if t not in STOPWORDS}

        def match_score(toks_a: set[str], toks_b: set[str]) -> float:
            score = float(len(toks_a & toks_b))
            for a in toks_a:
                for b in toks_b:
                    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
                        score += 0.5
            return score

        # Bucket entries by their section.
        entries_by_section: dict[int, list[dict]] = {}
        for entry in entries:
            sect_info = find_section(entry["category"])
            if sect_info is None:
                continue
            sid = id(sect_info)
            entries_by_section.setdefault(sid, []).append(entry)

        # Assign columns one-to-one within each section.
        entry_to_col: dict[str, int] = {}  # slug → column index in figure
        for sect_info in section_index_by_name.values():
            sid = id(sect_info)
            sect_entries = entries_by_section.get(sid, [])
            cols = sect_info["figure"].get("columns") or []
            if not cols or not sect_entries:
                continue
            entry_toks = {e["slug"]: tokens(e["title"]) for e in sect_entries}
            col_toks = {ci: tokens(lab) for ci, lab in enumerate(cols) if lab}
            # Score every (entry, column) pair.
            pairs: list[tuple[float, str, int]] = []
            for e in sect_entries:
                for ci, ct in col_toks.items():
                    s = match_score(entry_toks[e["slug"]], ct)
                    if s >= 0.5:
                        pairs.append((s, e["slug"], ci))
            pairs.sort(reverse=True)  # highest score first
            used_slugs: set[str] = set()
            used_cols: set[int] = set()
            for score, slug, ci in pairs:
                if slug in used_slugs or ci in used_cols:
                    continue
                entry_to_col[slug] = ci
                used_slugs.add(slug)
                used_cols.add(ci)

        processed = 0
        skipped = 0
        for entry in entries:
            slug = entry["slug"]
            md_path = OUT_DIR / f"{slug}.md"
            if md_path.exists() and not args.force:
                skipped += 1
                continue
            cat = entry["category"]
            sect_info = find_section(cat)
            if not sect_info:
                print(f"  [skip] no section match for {entry['title']} (cat={cat!r})")
                continue
            # Find this group's stats row by name (best-effort, case-insensitive,
            # token-overlap).
            wanted_tokens = set(re.findall(r"\w+", entry["title"].lower())) - {
                "and", "the", "of", "in", "for", "etc"
            }
            best_row = None
            best_score = 0
            for r in sect_info["rows"]:
                if r.get("name") == "Overall total":
                    continue
                row_tokens = set(re.findall(r"\w+", r["name"].lower()))
                score = len(wanted_tokens & row_tokens)
                if score > best_score:
                    best_score = score
                    best_row = r
            stats = stats_from_row(best_row["raw_cells"]) if best_row else {}

            # Per-group employed/growth — pull from the pre-computed
            # one-to-one entry→column assignment for this section.
            fig = sect_info["figure"]
            col_idx = entry_to_col.get(slug)
            if col_idx is not None:
                empl = fig.get("employed", [])
                grw = fig.get("growth_pct", [])
                if col_idx < len(empl):
                    stats["employed"] = empl[col_idx]
                if col_idx < len(grw):
                    stats["growth_pct"] = grw[col_idx]

            narrative = extract_group_narratives(sect_info["text"], [entry["title"]]).get(
                entry["title"], {"narrative": "", "shortage": ""}
            )

            sector_meta = {
                **sect_info["section"],
                **sect_info["figure"],
            }
            md = render_md(entry, stats, sector_meta, narrative, sect_info["outlook"])
            md_path.write_text(md)
            processed += 1

        print(f"Processed: {processed}, Skipped (cached): {skipped}")


if __name__ == "__main__":
    main()
