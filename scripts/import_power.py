"""Import NASA POWER files downloaded manually (JSON or CSV) and rebuild the processed dataset."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from earthscope import config
from earthscope.ingest import pipeline
from earthscope.qc import checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", help="downloaded .json or .csv files, or a folder of them")
    ap.add_argument("--location", help="location name if it cannot be read from the file name or coordinates")
    ap.add_argument("--assume-documented-units", action="store_true",
                    help="use the documented units ONLY when a file states none (recorded as an assumption)")
    args = ap.parse_args(argv)

    from pathlib import Path
    paths = []
    for f in args.files:
        p = Path(f)
        paths += sorted(p.glob("*.json")) + sorted(p.glob("*.csv")) if p.is_dir() else [p]
    try:
        copied = pipeline.import_files(paths, location=args.location,
                                       assume_documented_units=args.assume_documented_units)
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1
    for c in copied:
        print(f"[OK]   imported {c.name}")
    df = pipeline.build_processed(assume_documented_units=args.assume_documented_units)
    print(f"\nProcessed {len(df):,} rows for {df['location'].nunique()} location(s): "
          f"{', '.join(sorted(df['location'].unique()))}")
    print(f"Sources: {', '.join(sorted(df['source'].unique()))}")
    print("\nCompleteness:")
    print(checks.completeness(df).round({"pct_valid": 1}).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
