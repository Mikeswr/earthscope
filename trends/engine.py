"""Trend statistics with explicit handling of missing data and elapsed calendar time.

Design rules
1. Time is never reconstructed from array position. Annual series are indexed by integer
   year, monthly series by a DatetimeIndex, and every slope uses the actual elapsed years.
2. Missing values are removed only after their time coordinate is known, so gaps (missing
   months or whole missing years) never shift calendar identity or compress elapsed time.
3. Every test has documented minimum-data thresholds (constants below). A series that does
   not meet them returns trend "insufficient_data" with a reason, never a number.

Minimum valid observations
  Annual Mann-Kendall / Sen's slope   >= MIN_VALID_YEARS valid years AND valid years / year span
                                      >= MIN_YEAR_COVERAGE
  Seasonal Mann-Kendall               every calendar month needs >= MIN_YEARS_PER_MONTH valid years
                                      AND valid years / overall year span >= MIN_YEAR_COVERAGE
  Anomalies                           each calendar month needs >= MIN_BASE_YEARS valid years inside
                                      the base period, otherwise that month has no anomaly
"""
import numpy as np
import pandas as pd
from scipy.stats import norm, rankdata
from statsmodels.stats.multitest import multipletests

MIN_VALID_YEARS = 10
MIN_YEAR_COVERAGE = 0.70
MIN_YEARS_PER_MONTH = 10
MIN_BASE_YEARS = 20


# ---------------------------------------------------------------- building blocks
def mk_score(x):
    """Mann-Kendall S for values already ordered in time (depends on order only, not spacing)."""
    x = np.asarray(x, dtype=float)
    return float(np.triu(np.sign(x[None, :] - x[:, None]), 1).sum())


def mk_variance(x):
    """Var(S) with the standard tie correction."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    _, c = np.unique(x, return_counts=True)
    return (n * (n - 1) * (2 * n + 5) - np.sum(c * (c - 1) * (2 * c + 5))) / 18.0


def mk_z(s, var_s):
    if var_s <= 0:
        return 0.0
    if s > 0:
        return (s - 1) / np.sqrt(var_s)
    if s < 0:
        return (s + 1) / np.sqrt(var_s)
    return 0.0


def _verdict(z, alpha):
    p = float(2 * (1 - norm.cdf(abs(z))))
    if p < alpha:
        return p, ("increasing" if z > 0 else "decreasing")
    return p, "no trend"


def sens_slope(x, t):
    """Theil-Sen slope in units per time unit of t: median of (x_j - x_i) / (t_j - t_i) over all
    pairs with t_j > t_i. t carries the real elapsed time, so gaps are handled correctly."""
    x, t = np.asarray(x, dtype=float), np.asarray(t, dtype=float)
    i, j = np.triu_indices(len(x), 1)
    dt = t[j] - t[i]
    ok = dt > 0
    if not ok.any():
        return float("nan")
    return float(np.median((x[j] - x[i])[ok] / dt[ok]))


def hamed_rao_factor(x, t, slope, alpha=0.05):
    """Hamed and Rao (1998) variance inflation factor, computed on the real year grid.

    Ranks of the detrended series are placed on a regular yearly grid with NaN for missing
    years; lag-k autocorrelation uses only pairs where both years exist. Lags are limited to
    those with a positive weight (k <= n - 3), as in the original formulation."""
    n = len(x)
    if n < 4:
        return 1.0
    r = rankdata(x - slope * t)
    y = r - r.mean()
    t0 = int(t.min())
    span = int(t.max()) - t0 + 1
    grid = np.full(span, np.nan)
    grid[(t - t0).astype(int)] = y
    denom = np.sum(y ** 2) / n
    bound = norm.ppf(1 - alpha / 2) / np.sqrt(n)
    sni = 0.0
    for k in range(1, n - 2):
        if k >= span:
            break
        a, b = grid[:-k], grid[k:]
        m = ~np.isnan(a) & ~np.isnan(b)
        npair = int(m.sum())
        if npair < 3:
            continue
        rho = (np.sum(a[m] * b[m]) / npair) * ((span - k) / span) / denom
        if abs(rho) > bound:
            sni += (n - k) * (n - k - 1) * (n - k - 2) * rho
    return 1 + 2 / (n * (n - 1) * (n - 2)) * sni


def _lag1(x, t, slope):
    """Lag-1 autocorrelation of the Sen-detrended series from consecutive-year pairs (NaN if too few)."""
    n = len(x)
    if n < 6:
        return float("nan")
    d = x - slope * t
    d = d - d.mean()
    t0 = int(t.min())
    span = int(t.max()) - t0 + 1
    grid = np.full(span, np.nan)
    grid[(t - t0).astype(int)] = d
    a, b = grid[:-1], grid[1:]
    m = ~np.isnan(a) & ~np.isnan(b)
    npair = int(m.sum())
    if npair < 3:
        return float("nan")
    denom = np.sum(d ** 2) / n
    return float((np.sum(a[m] * b[m]) / npair) * ((span - 1) / span) / denom)


def sens_slope_ci(x, t, var_s, alpha=0.05):
    """Confidence interval for Sen's slope (Sen 1968 / Gilbert 1987) using Var(S), which the caller may
    have inflated for autocorrelation. Interpolates between the ranked pairwise slopes. Per time unit of t."""
    x, t = np.asarray(x, float), np.asarray(t, float)
    if not (np.isfinite(var_s) and var_s > 0):
        return float("nan"), float("nan")
    i, j = np.triu_indices(len(x), 1)
    dt = t[j] - t[i]
    sl = np.sort(((x[j] - x[i])[dt > 0]) / dt[dt > 0])
    big_n = len(sl)
    c = norm.ppf(1 - alpha / 2) * np.sqrt(var_s)
    lo_rank, hi_rank = (big_n - c) / 2.0, (big_n + c) / 2.0 + 1.0     # 1-based ranks
    def at(rank):
        rank = min(max(rank, 1.0), float(big_n))
        lo = int(np.floor(rank))
        hi = min(lo + 1, big_n)
        return float(sl[lo - 1] + (rank - lo) * (sl[hi - 1] - sl[lo - 1]))
    return at(lo_rank), at(hi_rank)


def ar1_neff_factor(x, t, slope):
    """Variance inflation from lag-1 autocorrelation (effective sample size approach).

    rho1 is estimated from the Sen-detrended series using only consecutive-year pairs that both
    exist; the AR(1)-implied autocorrelations rho1**k give  n / n_eff = 1 + 2 * sum_k (1 - k/n) rho1**k.
    The factor is floored at 1, so the correction can only make the test more cautious.
    In the simulations recorded in docs/METHODS.md this stayed close to the nominal error rate
    under AR(1) noise, where Hamed-Rao did not; that evidence is for AR(1) noise and n = 40."""
    n = len(x)
    rho = _lag1(x, t, slope)
    if rho != rho:
        return 1.0
    rho = float(np.clip(rho, -0.99, 0.99))
    k = np.arange(1, n)
    return max(1.0, float(1 + 2 * np.sum((1 - k / n) * rho ** k)))


def _year_series(series):
    """Returns (years, values, nominal_span) for the valid values.

    nominal_span is measured on the index AS GIVEN, before missing values are removed, so NaN years
    at the start, middle or end of the series still count as part of the record. Callers that want
    gaps to count must pass the full year range with NaN in the gaps."""
    s = pd.Series(series)
    if isinstance(s.index, pd.DatetimeIndex):
        raise TypeError("annual series must be indexed by integer year, not by date")
    t_all = np.asarray(s.index, dtype=float)
    if len(t_all) and not np.allclose(t_all, np.round(t_all)):
        raise ValueError("annual series index must be integer years")
    t_all = np.round(t_all).astype(int)
    if len(np.unique(t_all)) != len(t_all):
        raise ValueError("duplicate years in annual series")
    span = int(t_all.max() - t_all.min()) + 1 if len(t_all) else 0
    ok = s.notna().values
    t, x = t_all[ok], s.values.astype(float)[ok]
    order = np.argsort(t)
    return t[order], x[order], span


def _result(reason="", n=0, span=0, **kw):
    out = {"n": n, "n_span": span, "coverage": (n / span if span else np.nan),
           "trend": "insufficient_data" if reason else "", "p": np.nan, "z": np.nan, "tau": np.nan,
           "S": np.nan, "var_s": np.nan, "slope": np.nan, "variance_factor": np.nan, "reason": reason,
           "rho1": np.nan, "slope_ci_low": np.nan, "slope_ci_high": np.nan}
    out.update(kw)
    return out


# ---------------------------------------------------------------- public tests
def mann_kendall(series, alpha=0.05, autocorrelation="ar1_neff",
                 min_valid=MIN_VALID_YEARS, min_coverage=MIN_YEAR_COVERAGE):
    """Annual Mann-Kendall. series is indexed by integer year; NaN years are skipped.
    autocorrelation:
      'ar1_neff'   (default) variance inflation from lag-1 autocorrelation, floored at 1
      'hamed_rao'  Hamed and Rao (1998); matches pymannkendall on complete data but was
                   anticonservative in this project's simulations (docs/METHODS.md)
      'none'       plain Mann-Kendall, assumes independent years"""
    t, x, span = _year_series(series)
    n = len(x)
    if n < min_valid:
        return _result(f"only {n} valid years (need >= {min_valid})", n, span)
    if n / span < min_coverage:
        return _result(f"valid years cover {n / span:.0%} of the {span} year span (need >= {min_coverage:.0%})", n, span)
    s, var_s = mk_score(x), mk_variance(x)
    slope = sens_slope(x, t)
    factor = 1.0
    if autocorrelation == "ar1_neff":
        factor = ar1_neff_factor(x, t, slope)
    elif autocorrelation == "hamed_rao":
        factor = hamed_rao_factor(x, t, slope, alpha)
    elif autocorrelation != "none":
        raise ValueError("autocorrelation must be 'ar1_neff', 'hamed_rao' or 'none'")
    var_adj = var_s * factor
    if not var_adj > 0:
        return _result(f"variance after the {autocorrelation} correction is not positive (factor {factor:.3f}); "
                       "no p value can be computed", n, span, variance_factor=factor)
    z = mk_z(s, var_adj)
    p, trend = _verdict(z, alpha)
    lo, hi = sens_slope_ci(x, t, var_adj, alpha)
    return _result("", n, span, trend=trend, p=p, z=float(z), tau=s / (0.5 * n * (n - 1)),
                   S=s, var_s=var_adj, slope=slope, variance_factor=factor, autocorrelation=autocorrelation,
                   rho1=_lag1(x, t, slope), slope_ci_low=lo, slope_ci_high=hi)


def sens_slope_per_decade(annual, min_valid=MIN_VALID_YEARS, min_coverage=MIN_YEAR_COVERAGE):
    """Sen's slope per decade using actual elapsed years. NaN if thresholds are not met."""
    t, x, span = _year_series(annual)
    n = len(x)
    if n < min_valid or n / span < min_coverage:
        return float("nan")
    return sens_slope(x, t) * 10


def seasonal_mann_kendall(monthly, alpha=0.05, min_years_per_month=MIN_YEARS_PER_MONTH,
                          min_coverage=MIN_YEAR_COVERAGE):
    """Seasonal Mann-Kendall (Hirsch et al. 1982) with calendar-month identity preserved.

    S and Var(S) are computed within each calendar month across years and then summed.
    Months are treated as independent, so dependence between neighbouring months is NOT
    corrected here (see docs/METHODS.md). The slope is the median of all within-month
    pairwise slopes using real elapsed years, returned per year."""
    if not isinstance(monthly.index, pd.DatetimeIndex):
        raise TypeError("monthly series must have a DatetimeIndex")
    if monthly.index.duplicated().any():
        raise ValueError("duplicate months in monthly series")
    # nominal span comes from the full index, so NaN years at the start or end still count
    span = int(monthly.index.year.max() - monthly.index.year.min()) + 1 if len(monthly) else 0
    s = monthly.dropna()
    if s.empty:
        return _result("no valid data", 0, span)
    S = V = denom = 0.0
    slopes, counts = [], []
    for m in range(1, 13):
        g = s[s.index.month == m].sort_index()
        k = len(g)
        counts.append(k)
        if k < min_years_per_month:
            return _result(f"month {m:02d} has only {k} valid years (need >= {min_years_per_month})", int(len(s)), span,
                           min_years_in_a_month=min(counts))
        if k / span < min_coverage:
            return _result(f"month {m:02d} valid years cover {k / span:.0%} of the {span} year span "
                           f"(need >= {min_coverage:.0%})", int(len(s)), span, min_years_in_a_month=min(counts))
        yrs, x = g.index.year.values.astype(float), g.values.astype(float)
        S += mk_score(x)
        V += mk_variance(x)
        denom += 0.5 * k * (k - 1)
        i, j = np.triu_indices(k, 1)
        slopes.append((x[j] - x[i]) / (yrs[j] - yrs[i]))
    z = mk_z(S, V)
    p, trend = _verdict(z, alpha)
    return _result("", int(len(s)), span, trend=trend, p=p, z=float(z), tau=S / denom, S=S, var_s=V,
                   slope=float(np.median(np.concatenate(slopes))), variance_factor=1.0,
                   autocorrelation="none_between_months",
                   min_years_in_a_month=min(counts))


def climatology_anomalies(monthly, base=(1991, 2020), z_thresh=2.0, min_base_years=MIN_BASE_YEARS):
    """Anomalies against a monthly climatology from the base period of the SAME record.
    Every calendar month of the input is returned: missing or flagged months keep their position
    with NaN value, anomaly and z, and flag is False. A calendar month with fewer than
    min_base_years valid base-period values gets NaN anomalies."""
    df = monthly.to_frame("value")
    df["month"] = df.index.month
    ref = df[(df.index.year >= base[0]) & (df.index.year <= base[1])].dropna(subset=["value"])
    stats = ref.groupby("month")["value"].agg(["mean", "std", "count"])
    stats.loc[stats["count"] < min_base_years, ["mean", "std"]] = np.nan
    df = df.join(stats.rename(columns={"count": "clim_n"}), on="month")
    df["anomaly"] = df["value"] - df["mean"]
    df["z"] = df["anomaly"] / df["std"]
    df["flag"] = df["z"].abs() >= z_thresh
    return df[["value", "anomaly", "z", "flag", "clim_n"]]


def fdr_adjust(pvalues, alpha=0.05, method="bh"):
    """Adjusted p-values. 'bh' = Benjamini-Hochberg (independence or positive dependence);
    'by' = Benjamini-Yekutieli (any dependence, more conservative). NaNs are left out."""
    code = {"bh": "fdr_bh", "by": "fdr_by"}[method]
    p = np.asarray(pvalues, dtype=float)
    out = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    if ok.sum():
        out[ok] = multipletests(p[ok], alpha=alpha, method=code)[1]
    return out
