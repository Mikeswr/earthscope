"""Run trend analysis on the processed dataset and write results."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

import pandas as pd

from earthscope import config
from earthscope.ingest import pipeline
from earthscope.trends.pipeline import run_trends


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args(argv)
    src = config.processed_dir() / pipeline.PROCESSED_NAME
    if not src.exists():
        print(f"[FAIL] {src} not found. Run scripts/fetch_power.py or scripts/import_power.py first.")
        return 1
    df = pd.read_csv(src, parse_dates=["date"])
    trends, anoms = run_trends(df, alpha=args.alpha)
    trends.to_csv(config.processed_dir() / "trend_results.csv", index=False)
    anoms.to_csv(config.processed_dir() / "anomalies.csv", index=False)
    print(f"{len(trends)} series analysed, {int(trends['significant_fdr'].sum())} significant after FDR "
          f"(alpha={args.alpha}). {int(anoms['flag'].sum())} anomalous months flagged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
