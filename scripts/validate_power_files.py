"""Validate NASA POWER monthly point files BEFORE importing them. Nothing is imported or changed.

    python scripts/validate_power_files.py path/to/folder_or_files [--out-dir reports]

Writes preimport_validation.json and prints a summary. Exit code 1 if any check fails.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json

from earthscope import config
from earthscope.ingest import validate


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out-dir", default=str(config.ROOT / "reports"))
    args = ap.parse_args(argv)
    files = []
    for a in args.paths:
        p = Path(a)
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    locs = config.load_locations()
    results = [validate.validate_file(f, locs) for f in files]
    docs = {r["file"]: json.loads(Path(f).read_text()) for r, f in zip(results, files) if r.get("status") != "fail" or "header" in r}
    report = {"files": results, "cross_file": validate.compare_files(docs) if len(docs) > 1 else None}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "preimport_validation.json").write_text(json.dumps(report, indent=2, default=str))
    for r in results:
        print(f"{r['status'].upper():5s} {r['file']}  {r.get('counts', '')}")
        for x in r["checks"]:
            if x["status"] in ("fail", "warn"):
                print(f"        [{x['status']}] {x['check']}: {x['detail']}")
    print(f"\nreport: {out / 'preimport_validation.json'}")
    return 1 if any(r["status"] == "fail" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
