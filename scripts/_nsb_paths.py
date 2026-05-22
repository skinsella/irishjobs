"""
Shared helpers for locating the latest SOLAS National Skills Bulletin PDF.

Two responsibilities:

1. `discover_latest_nsb_url()` — scrape the SOLAS research landing page
   to find every `national-skills-bulletin-YYYY.pdf` link and return the
   highest-year (URL, year) pair. Used by `update.py` to spot when a
   new annual edition (NSB 2026, NSB 2027, …) appears.

2. `latest_local_nsb()` — return the path to the most recent NSB PDF
   already present in `raw/nsb_YYYY.pdf`. Used by every downstream
   parser (01_build_index, 03_parse_nsb) so they automatically pick up
   the newest cached bulletin without code changes.

Both functions are deterministic and idempotent.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

SOLAS_RESEARCH_URL = "https://www.solas.ie/research-lp/skills-labour-market-research-slmru/research/"
NSB_PDF_RE = re.compile(
    r"(?:https?:)?//a\.storyblok\.com/f/\d+/x/[a-z0-9]+/national-skills-bulletin-(\d{4})\.pdf",
    re.IGNORECASE,
)

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "raw"


def discover_latest_nsb_url(timeout: float = 30.0) -> tuple[str, int] | None:
    """Fetch the SOLAS landing page and return (url, year) for the highest-
    year NSB PDF linked, or None if the page can't be parsed."""
    try:
        r = httpx.get(SOLAS_RESEARCH_URL, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
    except Exception:
        return None
    found: list[tuple[int, str]] = []
    for m in NSB_PDF_RE.finditer(r.text):
        year = int(m.group(1))
        url = m.group(0)
        if url.startswith("//"):
            url = "https:" + url
        found.append((year, url))
    if not found:
        return None
    found.sort(reverse=True)
    year, url = found[0]
    return url, year


def latest_local_nsb() -> Path:
    """Return the path to the highest-year nsb_<year>.pdf in raw/.

    Raises FileNotFoundError if none is cached locally.
    """
    candidates = []
    for p in RAW.glob("nsb_*.pdf"):
        m = re.match(r"nsb_(\d{4})\.pdf", p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    if not candidates:
        raise FileNotFoundError(
            f"No nsb_YYYY.pdf cached in {RAW}. Run `update.py` first."
        )
    candidates.sort(reverse=True)
    return candidates[0][1]


def latest_local_nsb_year() -> int:
    return int(re.match(r"nsb_(\d{4})\.pdf", latest_local_nsb().name).group(1))


def latest_local_nsb_url() -> str | None:
    """Return the URL the latest NSB was downloaded from, or None if the
    sidecar .url file is missing (e.g. PDF was placed manually)."""
    pdf = latest_local_nsb()
    url_path = pdf.with_suffix(".url")
    if url_path.exists():
        return url_path.read_text().strip() or None
    return None
