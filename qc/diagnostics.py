"""QC diagnostics beyond range checks: suspicious values and homogeneity.
These flag things for a human to look at. They never change, remove or fill data."""
import numpy as np
import pandas as pd

from earthscope.trends import engine


def pettitt(series, alpha=0.05):
    """Pettitt (1979) change point test on an annual series indexed by integer year (NaN skipped).
    Returns dict: change_year (last year of the first segment), K, p (approximation), step (median after - median before).
    Assumes independent values: autocorrelation makes it over-detect, so treat a hit as a flag to inspect, not proof."""
    s = pd.Series(series).dropna()
    n = len(s)
    if n < 10:
        return {"n": n, "change_year": np.nan, "K": np.nan, "p": np.nan, "step": np.nan, "detected": False}
    x, yrs = s.values.astype(float), np.asarray(s.index)
    sg = np.sign(x[:, None] - x[None, :])
    u = np.array([sg[:t, t:].sum() for t in range(1, n)])
    k = int(np.abs(u).max())
    t_star = int(np.abs(u).argmax()) + 1
    p = float(min(1.0, 2 * np.exp(-6.0 * k ** 2 / (n ** 3 + n ** 2))))
    return {"n": n, "change_year": int(yrs[t_star - 1]), "K": k, "p": p,
            "step": float(np.median(x[t_star:]) - np.median(x[:t_star])), "detected": bool(p < alpha)}


def pettitt_detrended(series, alpha=0.05):
    """Pettitt test after removing the Sen linear trend (computed with the real years). A hit here means a step or
    other non-linear change remains beyond a straight line; a gradual trend alone no longer triggers it."""
    s = pd.Series(series).dropna()
    if len(s) < 10:
        return pettitt(s, alpha)
    t = np.asarray(s.index, dtype=float)
    slope = engine.sens_slope(s.values.astype(float), t)
    return pettitt(pd.Series(s.values - slope * t, index=s.index), alpha)


def runs_of_identical_values(values, min_run=4):
    """Lengths and positions (start index) of runs of identical consecutive values at least min_run long."""
    v = np.asarray(values, float)
    out, i = [], 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[j + 1] == v[i] and not np.isnan(v[i]):
            j += 1
        if j - i + 1 >= min_run:
            out.append((i, j - i + 1))
        i = j + 1
    return out


def suspicious_months(monthly, z_notable=3.0, z_extreme=4.0, base=(1991, 2020)):
    """Months whose anomaly against the calendar-month climatology is large, plus stuck-value runs.
    Returns (summary dict, DataFrame of the flagged months)."""
    a = engine.climatology_anomalies(monthly, base=base, z_thresh=z_notable)
    big = a[a["z"].abs() >= z_notable].copy()
    big["level"] = np.where(big["z"].abs() >= z_extreme, "extreme", "notable")
    runs = runs_of_identical_values(monthly.values)
    n_valid = int(a["z"].notna().sum())
    return ({"n_months_with_z": n_valid, "n_notable_abs_z_ge_3": int((a["z"].abs() >= z_notable).sum()),
             "n_extreme_abs_z_ge_4": int((a["z"].abs() >= z_extreme).sum()),
             "expected_abs_z_ge_3_if_normal": round(n_valid * 0.0027, 2), "n_identical_value_runs_ge_4": len(runs),
             "longest_identical_run": max([r[1] for r in runs], default=1)}, big)
