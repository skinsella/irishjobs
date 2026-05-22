# Ireland Jobs Market Visualizer — Plan

A port of Karpathy's `jobs-master` (US BLS Occupational Outlook Handbook
visualizer) to Ireland. Goal: same end product — an interactive treemap with
4 colour layers (Outlook / Pay / Education / Digital AI Exposure) over every
occupation in the Irish labour market, weighted by employment.

## 1. What the US pipeline does (recap)

| Stage | Script | Input → Output |
|-------|--------|----------------|
| Index | `parse_occupations.py` | BLS A–Z page → `occupations.json` (342 rows) |
| Scrape | `scrape.py` | Playwright fetches `html/<slug>.html` for every occupation |
| Parse to MD | `parse_detail.py` + `process.py` | Quick Facts table + tab content → `pages/<slug>.md` |
| Tabulate | `make_csv.py` | Pulls pay, education, jobs, outlook → `occupations.csv` |
| Score | `score.py` | OpenRouter LLM scores each MD → `scores.json` (exposure 0–10) |
| Build | `build_site_data.py` | Merge CSV + scores → `site/data.json` |
| Frontend | `site/index.html` | Squarified treemap (canvas, no framework) |

The treemap colours depend on five fields per occupation:
`title, category, jobs (employment count), pay (annual median), outlook (% growth), education (entry level), exposure (LLM score 0–10), exposure_rationale`.

## 2. Why Ireland doesn't map 1-to-1

There is **no Irish OOH** — no single public site with one HTML page per
occupation listing pay, education, growth, and a narrative description.
The same five fields live across several sources, but the data is **less
granular than the US**.

| US OOH field | Irish source | Granularity |
|--------------|--------------|-------------|
| Occupation list | SOLAS **National Skills Bulletin (NSB) 2025**, Section 10 + Appendix | ~80 NSB occupational groups, mapped to SOC2010 unit groups |
| Narrative description | NSB 2025 PDF (Section 10 profiles, ~1 page each) | per occupational group |
| Employment count | NSB Section 10 figures + CSO **QLF29** (cross-check at major-group level) | NSB ~80 groups; CSO public PxStat only 1-digit SOC |
| Outlook (growth) | NSB 5-yr annual growth rate (2019–2024) + shortage tag | per occupational group |
| Education | NSB %3rd-level field per group | percentage, not modal NFQ level |
| Median pay | **GAP** — no public SOC2010 × earnings table on CSO PxStat. Fallbacks below. | sector-level only |
| Category | NSB 16 sector chapters (10.1–10.16: Science & Eng, ICT, Business & Fin, Healthcare, Education, Social & Care, Legal & Security, Construction, Other Craft, Agriculture, Hospitality, Arts/Sport, Transport, Admin, Sales, Operatives & Elementary) | per group |
| AI exposure | Same LLM pipeline; feed NSB profile + stats to scorer | per group |

**Verified data findings (probed live):**
- `QLF29` (CSO PxStat): SOC2010 × quarter × sex × employment, but **only at 1-digit SOC**
  (11 major groups). Not granular enough to drive the treemap on its own.
- CSO public LFS tables do **not** publish SOC2010 unit-group employment.
  SOLAS SLMRU computes those numbers from CSO microdata (RMF access) and
  publishes the aggregates only inside the NSB itself. The NSB PDF is the
  effective primary source.
- CSO `DEN`/`EHQ` earnings tables are broken out by **NACE economic sector**,
  not by SOC occupation. There is no public occupation-level median earnings.
  No SOLAS supplementary Excel/CSV exists for NSB 2025.

**Pay-axis fallback strategy** (in order of preference):

1. **Sector-weighted average**: each NSB profile lists the share of
   employment by sector (e.g. "48% Industry, 19% Professional activities").
   Combine with CSO `DEN11`/`EHQ15` weekly earnings by NACE sector to
   produce a sector-weighted median earnings estimate per occupation.
2. **Census 2022 themes** (table `F1029`/`F1041` family): if these expose
   occupation × earnings at finer than 1-digit, use them as the primary
   source.
3. **Fallback**: label the layer "Sector-implied median pay" and disclose.

**Architectural consequence**: scrape one PDF (NSB 2025) + call a handful
of CSO PxStat tables for sectoral earnings cross-walks. No Playwright,
no per-occupation web pages.

## 3. Target directory layout

```
ireland-jobs/
├── README.md
├── PLAN.md                       (this file)
├── pyproject.toml                (httpx, pdfplumber, beautifulsoup4, python-dotenv, jsonstat.py)
├── raw/
│   ├── nsb_2025.pdf              (downloaded once)
│   └── pxstat/                   (cached JSON-stat responses, one file per table)
├── occupations.json              (master list: ~100 groups, slug/title/soc_codes/category)
├── pages/<slug>.md               (one MD per occupation: narrative + stats block)
├── occupations.csv               (one row per occupation, same schema as US)
├── scores.json                   (LLM AI-exposure scores, same schema)
├── scripts/
│   ├── 01_build_index.py         (NSB PDF → occupations.json)
│   ├── 02_fetch_cso.py           (PxStat API → raw/pxstat/*.json)
│   ├── 03_parse_nsb.py           (NSB profiles → pages/*.md)
│   ├── 04_make_csv.py            (merge NSB + CSO → occupations.csv)
│   ├── 05_score.py               (LLM scoring; identical to upstream)
│   └── 06_build_site_data.py     (CSV + scores → site/data.json)
└── site/
    ├── index.html                (clone of US site, re-tuned for Irish ranges)
    └── data.json
```

## 4. Stage-by-stage detail

### 4.1 Index (replaces `parse_occupations.py`)

Source: NSB 2025 PDF, Section 10 ("Occupational Profiles"). Each profile is
keyed by the SOLAS revised occupational grouping (≈100). Output:

```json
{
  "title": "Software developers",
  "slug": "software-developers",
  "soc_codes": ["2136", "2137"],
  "category": "professionals",
  "page_in_nsb": 167
}
```

Build by text-extracting the bulletin's table of contents + Appendix A
(SOC mapping), not by scraping a website.

### 4.2 Fetch (replaces `scrape.py`)

Two parallel fetchers (verified live):

1. **NSB 2025 PDF** — single download to `raw/nsb_2025.pdf` from
   `https://a.storyblok.com/f/70398/x/893ebacfd9/national-skills-bulletin-2025.pdf`.
   **This is the primary data source for the Irish version**, because no
   public Irish dataset has SOC2010 unit-group employment.

2. **CSO PxStat** — JSON-stat for cross-checks and sectoral pay weighting:
   - `QLF29` Persons aged 15-89 in employment by SOC2010 (1-digit, 11 major
     groups) × quarter × sex. Used to validate that NSB totals sum to LFS
     headlines.
   - `DEN11`/`DEN05` Median weekly earnings by NACE sector. Used as the
     sector-weighted earnings input for occupations.
   - `EHQ15` Average weekly/hourly earnings, all employees, by NACE sector.
     Cross-check on DEN.

   Endpoint pattern:
   `https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/{TBL}/JSON-stat/2.0/en`

   Cache each response to `raw/pxstat/<table>.json`. Idempotent.

### 4.3 Parse to Markdown (replaces `parse_detail.py` + `process.py`)

For each occupational group:
- Extract its profile text from the NSB PDF using `pdfplumber` keyed on the
  group heading.
- Aggregate matching SOC2010 unit-group rows from the PxStat tables.
- Emit `pages/<slug>.md` with the same shape as the US output (Quick Facts
  table, then narrative sections, then employment-projections block).

This MD is the input the LLM sees — it must read like an OOH page so the
existing exposure scoring rubric still applies cleanly.

### 4.4 Tabulate (replaces `make_csv.py`)

Pull structured fields out of the per-occupation data into `occupations.csv`
with the **same column names** the US site expects:

```
title, category, slug, soc_code, median_pay_annual, median_pay_hourly,
entry_education, work_experience, training, num_jobs_2024,
projected_employment_2034, outlook_pct, outlook_desc, employment_change, url
```

Two columns need definition for the Irish version:
- `outlook_pct` — % change in employment 2019 → 2024 from LFS (the bulletin's
  own series) **plus** a forward extrapolation. Honest alternative: use the
  observed 5-yr change as the "outlook" proxy and label it as such.
- `outlook_desc` — derive from the NSB's shortage/in-demand/surplus tag for
  the group (e.g. "Shortage", "In demand", "Stable", "Decline").
- `entry_education` — map the modal NFQ level from LFS to the same eight
  US strings the frontend expects (so the colour scale keeps working).
- `url` — link back to the NSB page anchor for that profile.

### 4.5 Score (re-use of `score.py`)

Upstream `score.py` is data-agnostic — it sends each `pages/<slug>.md` to
OpenRouter (default `google/gemini-3-flash-preview`) with a calibrated rubric.
Re-use it unchanged. Requires `OPENROUTER_API_KEY` in `.env`.

Optionally tighten the rubric for Ireland: the US examples ("software
developer 9/10") still apply but the system prompt could acknowledge
Ireland's heavy concentration in ICT, pharma, finance, and food sectors so
the LLM doesn't anchor on US occupational mix.

### 4.6 Build site data (replaces `build_site_data.py`)

Same merge logic. Output schema unchanged so `site/index.html` works.

### 4.7 Frontend (clone of `site/index.html`)

Minimal edits:
- Title → "Irish Job Market Visualizer".
- Total-jobs headline (currently "143M") becomes auto-computed (~2.7M).
- Pay axis range: shrink `payColor` log clamp from $25K–$250K to €20K–€150K.
- Education `EDU_LEVELS` array: re-label to NFQ levels (1–10) with the same
  ordinal property the colour scale relies on, OR keep US strings and map at
  build time. Either works; the latter is less invasive.
- "BLS Outlook" button → "CSO Outlook"; tooltip text references the NSB.
- Category labels in the treemap header → 9 SOC-2010 major groups.

## 5. Risks / open questions

1. **PDF parsing fragility**. NSB layout changes year to year. No Excel
   companion exists (confirmed live), so `pdfplumber` table extraction is
   the only path. Mitigation: write a defensive parser keyed on heading
   text + a manual review pass before trusting numbers.
2. **Granularity mismatch**. NSB groups (~100) are coarser than US OOH (342).
   The treemap will have ~100 tiles, which is fine visually. Optionally
   expand to SOC2010 unit-group level (~370) using CSO data alone — but then
   we lose narratives for LLM scoring on the long tail.
3. **Outlook definition**. US OOH publishes BLS 10-year projections;
   Ireland has no equivalent occupation-level projection. The honest fix is
   to label the colour as "5-yr historical change" (2019–2024) and disclose
   in the intro paragraph. EGFSN does sectoral forecasts but not at SOC
   unit-group level.
4. **Education encoding**. Irish data uses NFQ 1–10. Front-end currently
   hard-codes US strings. Cleanest: keep US strings and map NFQ → string
   (e.g. NFQ 8 = "Bachelor's degree"); cheapest, since the frontend stays
   intact.
5. **Earnings basis**. CSO EAADS is administrative data (Revenue P35 +
   PAYE), which is more reliable than survey medians but excludes
   self-employed. Note this in the methodology block.
6. **LLM cost**. ~100 occupations × ~2-3K tokens each ≈ negligible on
   Gemini Flash (under $1).

## 6. Execution order

1. Scaffold project + `pyproject.toml`.
2. Download NSB 2025 PDF.
3. Discover CSO PxStat table codes (small WebFetch / API probe).
4. Write `01_build_index.py` → produce `occupations.json` from NSB ToC.
5. Write `02_fetch_cso.py` → cache PxStat tables.
6. Write `03_parse_nsb.py` → produce all `pages/*.md`.
7. Write `04_make_csv.py` → produce `occupations.csv`.
8. Run `05_score.py` (re-used) → produce `scores.json`.
9. Write `06_build_site_data.py` → produce `site/data.json`.
10. Clone & adapt `site/index.html` with Irish labels & ranges.
11. Serve locally; sanity-check totals against published headline figures
    (employment ~2.7M, unemployment 4.3%, etc.).

## 7. Data sources (canonical URLs)

- SOLAS NSB 2025 PDF: https://a.storyblok.com/f/70398/x/893ebacfd9/national-skills-bulletin-2025.pdf
- CSO PxStat (JSON-stat API): https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/{TABLECODE}/JSON-stat/2.0/en
- CSO Earnings & Labour Costs landing: https://www.cso.ie/en/statistics/earnings/
- DETE Critical Skills Occupations List (Irish "in-demand" benchmark): https://enterprise.gov.ie/en/what-we-do/workplace-and-skills/employment-permits/employment-permit-eligibility/highly-skilled-eligible-occupations-list/
- EGFSN reports: https://www.skillsireland.ie/
