"""
Fetch reference data from CSO PxStat for cross-checks and sector-level
earnings. Mirrors the role of `scrape.py` in the US repo, but pulls
JSON-stat from a REST API instead of crawling HTML.

Tables fetched (verified to exist on CSO PxStat):
    QLF29 — Persons aged 15-89 in Employment by SOC2010 major group (1-digit)
    DEN11 — Median weekly earnings by NACE Rev.2 economic sector
    EHQ15 — Average weekly/hourly earnings by NACE Rev.2 sector

Each response is cached under raw/pxstat/<table>.json. Re-runs are
no-ops unless --force is passed.

Usage:
    uv run python scripts/02_fetch_cso.py
    uv run python scripts/02_fetch_cso.py --force
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "raw" / "pxstat"

API = (
    "https://ws.cso.ie/public/api.restful/"
    "PxStat.Data.Cube_API.ReadDataset/{table}/JSON-stat/2.0/en"
)

TABLES = {
    "QLF29": "Persons aged 15-89 years in Employment by SOC2010 major group",
    "DEN11": "Median weekly earnings by NACE Rev.2 sector",
    "EHQ15": "Average weekly/hourly earnings by NACE Rev.2 sector",
}


def fetch(client: httpx.Client, code: str, force: bool) -> Path:
    out = CACHE / f"{code}.json"
    if out.exists() and not force:
        print(f"  [{code}] cached ({out.stat().st_size:,} bytes)")
        return out
    url = API.format(table=code)
    print(f"  [{code}] GET {url}")
    r = client.get(url, timeout=60)
    r.raise_for_status()
    out.write_bytes(r.content)
    print(f"      → wrote {out.relative_to(REPO)} ({len(r.content):,} bytes)")
    return out


def summarise(path: Path) -> None:
    d = json.loads(path.read_text())
    print(f"      label   : {d.get('label')}")
    dims = d.get("dimension", {})
    print(f"      dims    : {', '.join(dims.keys())}")
    for k, v in dims.items():
        labels = list(v.get("category", {}).get("label", {}).values())
        print(f"        {k}: {len(labels)} categories")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if cached")
    args = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    with httpx.Client() as client:
        for code, desc in TABLES.items():
            print(f"\n{code}: {desc}")
            try:
                out = fetch(client, code, args.force)
                summarise(out)
            except Exception as e:
                print(f"      ERROR: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
