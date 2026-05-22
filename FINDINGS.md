# What the Irish data says about AI's impact on the economy

A reading of the 100 NSB occupational groups, the 2019–2024 LFS growth
rates, and the Friend-or-Foe two-axis exposure scores. Not a paper —
a working note on what the visible signal currently is.

## 1. There isn't one "AI exposure" story; there are two, and they go opposite ways

The single most important finding from putting Williamson et al.'s
two-axis framework into the data is that a *unidimensional* AI-exposure
score is incoherent. Programmers (complementary 9, substitutable 4) and
customer-service workers (complementary 4, substitutable 8) both score
"high" on a max-of-two view, but their futures look opposite:

| Axis (job-weighted) | Low (0–3) | High (7–10) | Δ |
|---|---|---|---|
| **Complementary** (AI augments) | +1.0% | **+6.8%** | +5.8pp |
| **Substitutable** (AI displaces) | +3.9% | **+2.2%** | −1.7pp |

The complementary axis correlates *positively* with employment growth.
The substitutable axis correlates *negatively*. Treating "AI exposure"
as a single number obscures the entire mechanism. The Department of
Finance's three-tier high/medium/low sector framework — which mixes
both axes — finds a 3.1pp gap between high-risk and low-risk sectors;
our occupation-level data on the substitutable axis alone finds a
−1.7pp gap, and on complementary, a +5.8pp gap. The combined effect is
real and visible in the LFS.

## 2. The net employment effect, so far, is a slowdown — not a decline

Even in the most substitutable occupations (score 7+ — telemarketers,
data clerks, basic customer service, routine document review), Irish
employment over 2019–2024 grew **+2.2%**. That is half the rate of
low-substitutable work but it is still positive. The Irish labour
market has not yet recorded an *absolute* AI displacement at the
sector level; what it has recorded is *missing growth* — hiring that
would have happened in a no-AI counterfactual, didn't.

This is consistent with the international evidence in the OECD's *AI
in Work* (2024), Anthropic's *Economic Index*, and Goldman Sachs's
labour-market series: at GPT-4-class capability AI does not yet fire
people; it slows replacement hiring. The visible labour-market story is
on the *margin* — at the rate of hiring, not at the level of
employment.

## 3. The age cut is the canary, and we can't reproduce it from public data

The Department of Finance's Box 4 chart — under-30 employment in ICT
fell **32%** from 2023Q1 to 2025Q4 while prime-age ICT employment
grew +7% — is the single most striking number in Irish data on this
question. It says the displacement is concentrated entirely at the
entry level. The intuition is mechanical: junior software-engineer
tasks (boilerplate code, unit tests, simple bug fixes) are precisely
what AI now does well; senior tasks (system design, code review, team
leadership, security architecture) it does not. So the bottom rung of
the ladder is closing faster than the rest of the ladder.

The implication: the *average worker* sees a productivity boost and
keeps their job. The *new entrant* doesn't get hired in the first
place. This is invisible in average-employment series and visible only
in age-cohort series. Reproducing it requires CSO microdata access
(RMF) which we don't have, so the visualiser cites the finding but
cannot independently confirm it. This is the most important place for
follow-up research and the most consequential single number in the
debate.

## 4. AI widens the pay distribution in three directions at once

Cross-tabbing the AI exposure axes with the Q3 2025 sector-weighted
pay shows a polarising pattern:

- **High complementary, high pay** (~€60–80K): software developers,
  finance professionals, scientists, lawyers. AI is making them more
  productive *and* the market is bidding up their compensation.
- **High substitutable, mid pay** (~€30–50K): customer-service reps,
  administrators, paralegals, basic accountants, sales clerks. AI is
  pressuring both demand and price for their labour.
- **Low exposure, low pay** (~€25–35K): chefs, carers, hairdressers,
  electricians, plumbers. AI is largely irrelevant to their work; pay
  is rising only with national wage drift.

Result: the wage distribution stretches at both ends. Classical
skill-biased technical change predicts widening top-vs-middle; this
data suggests AI is *also* protecting the bottom (because physical and
care work remain stubbornly human). The middle is the squeeze. That
matters politically — the historical "middle of the income
distribution" in Ireland is heavy in administrative, clerical, and
retail work, which is exactly where the substitutable axis lights up.

## 5. Ireland is unusually exposed, and is also where the AI infrastructure lives

Two facts together make Ireland a natural laboratory for the
early-effects question. First, it is a knowledge-services-heavy economy:
ICT, finance, and professional-scientific-technical sectors together
employ around a quarter of the workforce, vs an OECD median closer to
17%. The DoF estimates 63% of Irish employment is "relatively
AI-exposed" against an advanced-economy average closer to 45%. Our
occupation-level tier breakdown puts ~62% in high-or-medium risk,
which matches.

Second, Ireland is also the *physical host* of much of the AI
infrastructure driving the disruption — the FLAP-D data-centre group
(Frankfurt, London, Amsterdam, Paris, **Dublin**), €1.9B of AI-related
hardware imports in Q4 2025 alone, and a sizeable share of the
multinationals (Google, Meta, Microsoft, Amazon) whose products are
displacing the very clerical and customer-service roles the
substitutable axis lights up. This makes Ireland one of the few
countries where the macro-investment story and the micro-labour story
are unfolding in the same jurisdiction at the same time.

## 6. What the data cannot tell us yet

Three honest negative answers. **(a) What happens at the next AI capability
step.** All the empirical exposure work — Eloundou et al., Felten et al.,
the Friend-or-Foe paper — is calibrated to roughly GPT-4-level
capability. If GPT-6 or its successors can reliably perform what we
currently rate "substitutable" tasks, the −1.7pp gap could open into
a genuine absolute decline. The visualiser would catch this in the
next 2027 LFS release if it happens. **(b) Whether the complementary
"premium" is durable or one-off.** The +6.8% growth for
high-complementary occupations may be partly demand catch-up (every
firm wanting AI-augmented workers right now) rather than a permanent
productivity effect. We won't know until we have 2026 and 2027 data.
**(c) Whether the under-30 squeeze persists.** If new entrants reroute
into augmented occupations the cohort effect should fade; if they
can't, we are looking at a generational scar.

## 7. Implications, briefly

For *workers*: the complementary axis is the actionable signal. Choosing
or moving into a high-complementary occupation appears to be the
single most consequential career hedge in this data. The
high-substitutable, mid-pay band is the dangerous zone.

For *firms*: the productivity dividend in the high-complementary cluster
is the strategic story — Ireland's ICT sector grew employment 9.8% per
year over 2019–2024 while presumably becoming materially more
productive per worker, and is hiring at the senior end while
contracting at the junior end. Workforce planning has to address that
inverted pyramid before it becomes a 2030 succession problem.

For *policymakers*: the displacement is showing up exactly where active
labour-market policy is supposed to work — at the hiring margin, for
younger workers, in routinised cognitive work. Ireland's FET system,
the EGFSN's skills work, and SOLAS's reskilling brief are well-placed
in principle; whether they are positioned for the specific occupations
the substitutable axis flags (customer-service supervisors, payroll
clerks, basic accountants, paralegals) is an empirical question worth
asking.

For *researchers*: the under-30 ICT chart from DoF Box 4 is the single
most important Irish labour-market finding on AI to date and deserves
sustained replication with each new LFS quarter. Ireland is one of the
first places this signal is visible, and the visualiser is set up to
re-run automatically every month so the time-series can be tracked as
new data arrives.

---

*Drawn from the [Irish Job Market Visualiser](https://stephenkinsella.net/irishjobs/),
SOLAS National Skills Bulletin 2025, CSO LFS (QLF29 / EHQ15), and the
Department of Finance "AI: Friend or Foe?" framework. All numerical
claims trace to public data — see the
[data-lineage ledger](https://github.com/skinsella/irishjobs#data-lineage--every-figure-on-screen-every-source)
for sources. May 2026.*
