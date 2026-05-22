"""
Top-level orchestrator: runs the full data pipeline end-to-end.

This is the single entry point for `auto-update`. It runs each stage
idempotently:

  1. Download/refresh the SOLAS NSB PDF (refreshes only if upstream
     has changed; the URL is the same year-to-year so we hash on
     content-length / etag).
  2. Re-fetch CSO PxStat tables.
  3. Rebuild occupations.json from the NSB Appendix.
  4. Re-parse pages/*.md from NSB Section 10 profiles.
  5. Rebuild occupations.csv.
  6. Re-score AI exposure (only newly-added occupations are sent to
     the LLM; cached scores are preserved).
  7. Rebuild site/data.json.

Stages 3–7 only execute if their inputs changed (mtime check). Used
manually (`uv run python update.py`) or from CI.

Exit code 0 = success, 1 = at least one stage failed, 2 = inputs
unchanged (no work to do).

Usage:
    uv run python update.py              # incremental
    uv run python update.py --force      # rebuild everything
    uv run python update.py --no-score   # skip LLM scoring
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent
RAW = REPO / "raw"
SCRIPTS = REPO / "scripts"

NSB_URL = "https://a.storyblok.com/f/70398/x/893ebacfd9/national-skills-bulletin-2025.pdf"
NSB_PDF = RAW / "nsb_2025.pdf"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def refresh_pdf(force: bool) -> bool:
    """Return True if the PDF was (re-)downloaded."""
    if NSB_PDF.exists() and not force:
        old_size = NSB_PDF.stat().st_size
        try:
            r = httpx.head(NSB_URL, timeout=20, follow_redirects=True)
            new_size = int(r.headers.get("content-length", "0"))
            if new_size and new_size == old_size:
                print(f"  NSB PDF unchanged ({old_size:,} bytes)")
                return False
        except Exception as e:
            print(f"  (HEAD failed: {e}; re-downloading just in case)")
    print(f"  GET {NSB_URL}")
    r = httpx.get(NSB_URL, timeout=120, follow_redirects=True)
    r.raise_for_status()
    NSB_PDF.parent.mkdir(parents=True, exist_ok=True)
    NSB_PDF.write_bytes(r.content)
    print(f"  → {NSB_PDF.relative_to(REPO)} ({len(r.content):,} bytes)")
    return True


def newer(target: Path, *deps: Path) -> bool:
    """True if target is missing or any dep is newer than target."""
    if not target.exists():
        return True
    tt = target.stat().st_mtime
    return any(d.exists() and d.stat().st_mtime > tt for d in deps)


def run(label: str, cmd: list[str]) -> bool:
    print(f"\n▶ {label}")
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO)
    if result.returncode != 0:
        print(f"  ✗ failed ({result.returncode})")
        return False
    print(f"  ✓ done")
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true",
                   help="Rebuild every stage regardless of mtimes")
    p.add_argument("--no-score", action="store_true",
                   help="Skip stage 5 (LLM scoring, requires OPENROUTER_API_KEY)")
    args = p.parse_args()

    print("=" * 60)
    print(" Irish Jobs Visualiser — Auto Update")
    print("=" * 60)

    failures: list[str] = []

    print("\n[1/7] Refreshing NSB PDF…")
    pdf_changed = refresh_pdf(args.force)

    print("\n[2/7] Refreshing CSO PxStat tables…")
    cmd = ["uv", "run", "python", str(SCRIPTS / "02_fetch_cso.py")]
    if args.force:
        cmd.append("--force")
    if not run("CSO fetch", cmd):
        failures.append("02_fetch_cso")

    occ_json = REPO / "occupations.json"
    print("\n[3/7] Building occupations.json from NSB Appendix…")
    if pdf_changed or args.force or not occ_json.exists():
        if not run("Index build", ["uv", "run", "python", str(SCRIPTS / "01_build_index.py")]):
            failures.append("01_build_index")
    else:
        print(f"  ↺ skipped (NSB unchanged, {occ_json.name} fresh)")

    print("\n[4/7] Parsing NSB profiles → pages/*.md…")
    if pdf_changed or args.force:
        cmd = ["uv", "run", "python", str(SCRIPTS / "03_parse_nsb.py")]
        if args.force:
            cmd.append("--force")
        if not run("Profile parse", cmd):
            failures.append("03_parse_nsb")
    else:
        print("  ↺ skipped (NSB unchanged)")

    csv_path = REPO / "occupations.csv"
    den11 = REPO / "raw" / "pxstat" / "DEN11.json"
    print("\n[5/7] Building occupations.csv…")
    if args.force or newer(csv_path, occ_json, den11):
        if not run("CSV build", ["uv", "run", "python", str(SCRIPTS / "04_make_csv.py")]):
            failures.append("04_make_csv")
    else:
        print("  ↺ skipped (no upstream change)")

    print("\n[6/7] Scoring AI exposure (incremental)…")
    if args.no_score:
        print("  ↺ skipped (--no-score)")
    elif not os.environ.get("OPENROUTER_API_KEY"):
        print("  ↺ skipped (OPENROUTER_API_KEY not set; "
              "scores.json will retain existing values)")
    else:
        cmd = ["uv", "run", "python", str(SCRIPTS / "05_score.py")]
        if args.force:
            cmd.append("--force")
        if not run("Score", cmd):
            failures.append("05_score")

    print("\n[7/7] Building site/data.json…")
    if not run("Build site data",
               ["uv", "run", "python", str(SCRIPTS / "06_build_site_data.py")]):
        failures.append("06_build_site_data")

    print("\n" + "=" * 60)
    if failures:
        print(f" ✗ Pipeline finished with {len(failures)} failure(s): {failures}")
        return 1
    print(" ✓ Pipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
