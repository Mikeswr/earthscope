import json

import pandas as pd

from earthscope import config
from earthscope.ingest.pipeline import METADATA_NAME, PROCESSED_NAME
from earthscope.trends.pipeline import run_trends


def load_data():
    """Returns dict with df, trends, anoms, meta or None when no processed data exists."""
    pdir = config.processed_dir()
    src = pdir / PROCESSED_NAME
    if not src.exists():
        return None
    df = pd.read_csv(src, parse_dates=["date"])
    tp, ap = pdir / "trend_results.csv", pdir / "anomalies.csv"
    if tp.exists() and ap.exists() and tp.stat().st_mtime >= src.stat().st_mtime:
        trends, anoms = pd.read_csv(tp), pd.read_csv(ap, parse_dates=["date"])
    else:
        trends, anoms = run_trends(df)
    mp = pdir / METADATA_NAME
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    return {"df": df, "trends": trends, "anoms": anoms, "meta": meta}
