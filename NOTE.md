# Irish Job Market Visualiser — a short note

**Live at:** http://stephenkinsella.net/irishjobs/ &nbsp;·&nbsp; **Code:** https://github.com/skinsella/irishjobs

This is a small research tool that visualises Ireland's labour market as
an interactive treemap. Every rectangle is one of the ~100 occupational
groups that SOLAS reports on in its annual National Skills Bulletin;
each rectangle's *area* is proportional to that group's employment
(currently 2.6M of the 2.76M LFS-reported workforce, since the NSB does
not classify every worker into its 16 chapters), and its *colour* shows
the metric you select — five-year employment growth, sector-weighted
median pay, education profile, or AI exposure. It is a port to Irish
data of [Andrej Karpathy's US-BLS jobs visualiser](https://karpathy.ai/jobs/),
re-engineered around the more limited public statistics Ireland makes
available.

The novel piece is the **AI exposure layer**. Following the Department
of Finance's *Friend or Foe?* framework (Williamson et al., 2024) and
its more recent *Economic Insights Vol. 1 2026* update, exposure is
split into two independent 0–10 axes: *complementary* (AI augments the
worker) and *substitutable* (AI displaces the work). The scores come
from an LLM rubric calibrated against a 12-occupation anchor grid; the
site backtests them against the actual 2019–2024 LFS growth rates and
finds that high-substitutable occupations grew at +2.2% vs +3.9% for
low-substitutable, in the same direction as the DoF's published
sector-level 3.1% vs 6.2% finding. The treemap therefore shows a
*data-validated* AI exposure signal, not an arbitrary model judgement.

A few honest limits are documented in the on-site lineage block and the
[README](https://github.com/skinsella/irishjobs#data-lineage--every-figure-on-screen-every-source).
The pay layer is sector-weighted from CSO sector-level data (Q3 2025
EHQ15) rather than occupation-specific — Ireland publishes no
SOC2010-by-earnings table. The "outlook" is historical five-year growth
(2019–2024), not a forward projection — Ireland has no equivalent of
the BLS ten-year forecast. The pipeline is fully automated: a monthly
GitHub Actions job re-scrapes the SOLAS landing page, picks up any new
NSB edition automatically (NSB 2026 is expected October 2026), re-runs
all six processing scripts, re-scores AI exposure on anything new, and
redeploys the static site. The whole system is intentionally cheap to
run, transparent about every derived number, and easy to fork for any
country that publishes equivalent occupational statistics.
