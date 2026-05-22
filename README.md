# Irish Job Market Visualiser

Port of [karpathy/jobs](https://karpathy.ai/jobs/) to Irish data. Same end
product — interactive treemap with four colour layers (5-yr growth, median
pay, education profile, AI exposure) — but backed by the SOLAS National
Skills Bulletin and CSO PxStat instead of the US BLS Occupational Outlook
Handbook.

See [PLAN.md](PLAN.md) for the architecture and the data-source trade-offs
that drove it.

## Architecture

```
NSB 2025 PDF  ──┐
                ├──→ 01_build_index ─→ occupations.json
                └──→ 03_parse_nsb   ─→ pages/*.md  ─→ 05_score ─→ scores.json
                                                ↓
CSO PxStat   ──── 02_fetch_cso   ───→ raw/pxstat/*.json
                                                ↓
                            04_make_csv ─→ occupations.csv
                                                ↓
                       06_build_site_data ─→ site/data.json
                                                ↓
                                      site/index.html (canvas treemap)
```

## Auto-update

The pipeline is fully automated and idempotent:

- `update.py` runs every stage end-to-end, skipping stages whose inputs
  haven't changed (mtime checks). On a fresh checkout it builds the
  whole site in ~30s (excluding the LLM scoring step).
- `.github/workflows/refresh.yml` runs the pipeline on the **1st of
  every month**, on `workflow_dispatch`, and on every push to `main`
  that touches scripts/site. The workflow:
  1. `uv sync` + `uv run python update.py`
  2. Commits any changed artefacts (raw/, occupations.json,
     occupations.csv, pages/, site/data.json, scores.json) back to main
  3. Publishes `site/` to GitHub Pages

Add an `OPENROUTER_API_KEY` repo secret to enable the AI-exposure
scoring step in CI. Without the key, the workflow still runs all other
stages and serves a treemap with the exposure colour layer disabled.

## Local usage

```
uv sync                      # one-time

uv run python update.py      # incremental refresh (everything except scoring)
uv run python update.py --force      # rebuild everything
uv run python update.py --no-score   # skip LLM scoring even if key is present
```

To enable scoring locally, put your OpenRouter key in `.env`:

```
OPENROUTER_API_KEY=sk-or-...
```

Then `uv run python scripts/05_score.py` (or remove `--no-score` from
`update.py`).

## Serving the site locally

```
cd site && python -m http.server 8000
# open http://localhost:8000
```

## Data sources

| Source | Used for | Cadence |
|--------|----------|---------|
| [SOLAS National Skills Bulletin 2025](https://a.storyblok.com/f/70398/x/893ebacfd9/national-skills-bulletin-2025.pdf) | 100 occupational groups, employment counts, 5-yr growth, %female/FT/55+/Irish/3rd-level, shortage tags, narrative profiles, SOC2010 mapping (Appendix) | Annual (October) |
| [CSO PxStat `QLF29`](https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/QLF29/JSON-stat/2.0/en) | LFS employment by SOC2010 major group — cross-check on NSB totals | Quarterly |
| [CSO PxStat `DEN11`](https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/DEN11/JSON-stat/2.0/en) | Median weekly earnings by NACE sector — used for the sector-weighted pay estimate | Annual |
| [CSO PxStat `EHQ15`](https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/EHQ15/JSON-stat/2.0/en) | Average earnings by NACE sector — cross-check on DEN11 | Quarterly |
| OpenRouter (Gemini Flash) | LLM-based AI Exposure score per occupation | On-demand |

## AI exposure: Friend-or-Foe two-axis framework

Following the Department of Finance / DETE framework in **Williamson,
Gannon, Daly, Fitzgerald and Coates (2024)** ["Artificial Intelligence:
Friend or Foe? A Review of How AI Could Impact Ireland's Labour
Market"](https://assets.gov.ie/static/documents/artificial-intelligence-friend-or-foe-an-analysis-of-how-ai-could-impact-irelands-labo.pdf)
and the [Department of Finance Economic Insights Volume 1
2026](https://assets.gov.ie/static/documents/391b8952/Economic_Insights_Volume_1_2026.pdf),
this site separates AI exposure into two independent 0–10 axes:

- **Complementary** — AI makes the worker more productive (the worker
  stays). Software developers: 9/10.
- **Substitutable** — AI displaces the work (the worker goes). Data
  entry clerks: 10/10. Customer service: 8/10.

The same role can be high on both at once (paralegals, copywriters:
~7/7). The original "Digital AI Exposure" single-number toggle is kept
as `max(comp, subst)` for visual comparability with karpathy/jobs.

Each occupation is also tagged with the Department of Finance's
**high / medium / low** sector risk tier, shown as a coloured badge in
the tile tooltip. The DoF's published empirical work shows high-risk
sectors grew employment by only 3.1% in 2023–2025 vs 6.2% in low-risk
sectors, with under-30 ICT employment falling **32%** over the same
window — the dataset's most striking finding and the strongest single
piece of evidence that AI labour-market effects are already visible
in Irish data.

## Data lineage — every figure on screen, every source

Each field in `site/data.json` (the only data the frontend reads) is one of:

| Field | Type | Source | Status |
|-------|------|--------|--------|
| `title` | string | NSB 2025 Appendix, middle column (parsed from PDF) | ✓ real |
| `slug` | string | Deterministic slugify of `title` | ✓ derived from real |
| `category` | string | NSB 2025 Appendix, leftmost column (parsed from PDF) | ✓ real |
| `jobs` | int | NSB Section 10 "Annual Average Employment 2024" figure — number printed under each bar in the chart | ✓ real (94/100; 6 groups unmatched, shown as null) |
| `outlook` | int (%) | NSB Section 10 "Annual Average Growth Rates 2019–2024" figure — percentage printed under each bar | ✓ real (93/100) |
| `outlook_desc` | string | **Derived classification** from `outlook` using internal thresholds: ≥5% "Much faster", ≥3% "Faster", ≥1% "As fast as", ≥0% "Slower", else "Decline" | ⚠ derived, not published |
| `pay` | int (€/yr) | **Sector-weighted estimate**: CSO DEN11 median weekly earnings 2024 × NSB main-NACE-sector mix × 52 weeks. No occupation-specific median exists in public Irish data. | ⚠ derived, not published |
| `education` | string | **Derived classification** from NSB "% Third-level graduates" via internal thresholds (≥90% "Doctoral/Professional"; ≥80% "Master's"; ≥60% "Bachelor's"; …). Empty for the 60 groups where the parser couldn't extract the %3rd-level field from the NSB indicator table. | ⚠ derived, not published |
| `exposure_complementary` | int 0–10 | OpenRouter LLM (Gemini Flash) given the per-group NSB profile; calibrated against a 12-occupation anchor grid from Williamson et al. (2024) | ⚠ model estimate, not data |
| `exposure_substitutable` | int 0–10 | Same | ⚠ model estimate |
| `exposure` | int 0–10 | `max(complementary, substitutable)` | ⚠ derived from model |
| `exposure_rationale` | string | LLM output | ⚠ model output |
| `dof_risk_tier` | string ∈ {high, medium, low} | **Hand-coded mapping** from NSB sector → DoF risk tier, calibrated against Williamson et al. (2024). DoF did not publish per-NSB-sector tiers directly; the mapping is documented in `DOF_RISK_TIER` in [scripts/04_make_csv.py](scripts/04_make_csv.py) | ⚠ judgment from real framework |
| `url` | string | Hardcoded to the NSB landing page (the PDF has no per-occupation deep-links) | ⚠ same URL for all 100 |

**Hardcoded constants used in derivations (all national-average defaults, no per-occupation guessing):**

- `weeks_per_year = 52` (annual = weekly × 52)
- `hours_per_week = 39` (hourly = weekly ÷ 39; CSO's Irish full-time avg ~38.5h)

**Fields where the parser previously hallucinated and have been removed:**

- ~~`Skills shortage assessment` row in `pages/*.md`~~ — NSB 2-column-layout text capture was misattributing carpenters' narrative to plumbers and a generic "Nurses" header to nurses-midwives. Until the parser is rewritten with x-coordinate-aware column splitting, the shortage tag is **not emitted** anywhere downstream and `outlook_desc` falls back to the percentage-band classification. Audit revealed this 2-row contamination on 2026-05-22; fix landed in commit [TBD] of this push.
- ~~`Occupation-level outlook` per-group narrative~~ — same root cause; suppressed for the same reason. The sector-level outlook paragraph (which IS reliable) is kept.

**What the LLM saw:** the AI exposure scores were generated against the per-occupation Markdown that contains the Quick Facts table (real NSB figures), the SOC unit-group list, the sector context block, and the sector-level outlook narrative — all of which trace to real NSB data. The garbage shortage tag was present in the LLM input for nurses + plumbers only, and a spot check shows the resulting scores (Nurses comp=7/subst=1; Plumbers comp=1/subst=0) are still sensible — the model treated the contamination as low-signal text. No re-scoring was needed.

**What was checked, what is not in this codebase:**

- Probed CSO PxStat for any public table cross-tabulating SOC2010 occupation × age, NACE sector × age, and NACE × age × time — **none exist publicly**. The Department of Finance's striking under-30 ICT chart (Figure 10B of Box 4, "AI and the Irish labour market") was computed from CSO microdata under RMF access, which is not on PxStat. The finding is cited in the intro paragraph but **not reproduced** in this site; reproducing it would require fabricating an age trend, which we have not done.

## Methodological caveats

The Irish data is less granular than the US BLS data. See [PLAN.md §2](PLAN.md)
for the full discussion. The two important caveats surfaced in the
frontend intro paragraph:

1. **Pay is sector-weighted**, not occupation-specific. CSO doesn't publish
   median earnings by SOC2010 occupation, so we combine each occupation's
   NSB sector mix with DEN11 sector medians.
2. **Outlook is 5-yr historical growth**, not a forward projection.
   Ireland has no equivalent of BLS's 10-year occupational projection.
3. **Risk tiers are sector-level**, mapped from DoF's NACE-sector
   analysis onto the NSB's occupational chapters. An ICT specialist
   inherits a `high` tier from the ICT sector even though the specialist
   could be a niche security architect with a low individual exposure.
   See `DOF_RISK_TIER` in
   [scripts/04_make_csv.py](scripts/04_make_csv.py) to override the
   mapping.
4. **The total employment shown (~2.6M) is below the CSO LFS headline
   of ~2.76M.** Two reasons. (a) The NSB itself only classifies ~2.66M
   workers into its 16 occupational chapters — armed forces, workers
   with undisclosed SOC codes, and a handful of small-N categories
   sit outside. (b) The parser cannot match every NSB occupational
   group to a chart column when the labels are heavily abbreviated
   (typically 6 of 100 groups end up without an employment value), so
   we under-count by another ~50K. The treemap tile for those groups
   shows no employment. Improving the bar-chart column-label OCR
   would close most of the gap.
4. **No age × occupation data** is publicly available from CSO — the
   DoF's under-30 employment chart was computed from microdata under
   their RMF access. We cannot reproduce the age-cohort split at the
   occupation level from public sources.

## Status

Pipeline runs end-to-end. 100 occupational groups indexed, 98 with
employment counts, 100 with pay estimates, 97 with outlook, 40 with
education tier (partial — depends on NSB indicator-table coverage).
LLM scoring requires an OpenRouter key.
