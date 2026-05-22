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

## Methodological caveats

The Irish data is less granular than the US BLS data. See [PLAN.md §2](PLAN.md)
for the full discussion. The two important caveats surfaced in the
frontend intro paragraph:

1. **Pay is sector-weighted**, not occupation-specific. CSO doesn't publish
   median earnings by SOC2010 occupation, so we combine each occupation's
   NSB sector mix with DEN11 sector medians.
2. **Outlook is 5-yr historical growth**, not a forward projection.
   Ireland has no equivalent of BLS's 10-year occupational projection.

## Status

Pipeline runs end-to-end. 100 occupational groups indexed, 98 with
employment counts, 100 with pay estimates, 97 with outlook, 40 with
education tier (partial — depends on NSB indicator-table coverage).
LLM scoring requires an OpenRouter key.
