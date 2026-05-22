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
