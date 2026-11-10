"""Run the trend engine over the standardised dataset."""
import numpy as np
import pandas as pd

from earthscope import config
from earthscope.trends import engine

MIN_MONTHS_PER_YEAR = 12   # annual value requires all 12 valid months (see docs/METHODS.md)


def monthly_series(group):
    """Monthly values on the COMPLETE regular index from the first to the last date present in the
    group, whatever the QC flag. Values flagged missing or out_of_range become NaN at their own
    calendar position. Nothing is removed, so the date range never shrinks, even when whole years
    at the start, middle or end are flagged. Months absent from the input are NaN as well."""
    if group.empty:
        return pd.Series(dtype=float)
    if group["date"].duplicated().any():
        raise ValueError("duplicate dates in one location and variable")
    g = group.set_index("date").sort_index()
    s = g["value"].where(g["qc_flag"] == "ok")
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="MS"))


def annual_series(monthly, min_months=MIN_MONTHS_PER_YEAR, how="day_weighted_mean"):
    """Annual value from the 12 monthly values. Index = every integer year from the first to the last
    year of the input, so years with too little data stay in the series as NaN.
    how: 'day_weighted_mean' (mean weighted by days in each month), 'max' or 'min' (annual extreme of the
    monthly values). A year needs at least min_months valid months (12 by default)."""
    if monthly.empty:
        return pd.Series(dtype=float)
    yrs = monthly.index.year
    valid = monthly.notna()
    cnt = valid.groupby(yrs).sum()
    if how == "day_weighted_mean":
        days = pd.Series(monthly.index.days_in_month, index=monthly.index, dtype=float)
        num = (monthly.fillna(0) * days).groupby(yrs).sum()
        den = days.where(valid, 0).groupby(yrs).sum()
        ann = num / den.replace(0, np.nan)
    elif how == "max":
        ann = monthly.groupby(yrs).max()
    elif how == "min":
        ann = monthly.groupby(yrs).min()
    else:
        raise ValueError("how must be 'day_weighted_mean', 'max' or 'min'")
    ann[cnt < min_months] = np.nan
    ann.index = ann.index.astype(int)
    return ann.reindex(range(int(ann.index.min()), int(ann.index.max()) + 1))


def run_trends(df, alpha=0.05, base=(1991, 2020), min_months=MIN_MONTHS_PER_YEAR, fdr_method="bh",
               autocorrelation="ar1_neff", aggregation=None, fdr_families=None):
    """Returns (trend_table, anomaly_table).
    aggregation: optional {variable: how} overriding config.ANNUAL_AGGREGATION (used for sensitivity runs).
    fdr_families: optional {variable: family}; FDR is applied within each family (default config.FDR_FAMILIES,
    everything else is the primary family)."""
    rows, anoms = [], []
    families = config.FDR_FAMILIES if fdr_families is None else fdr_families
    for (loc, var), g in df.groupby(["location", "variable"]):
        m = monthly_series(g)
        how = (aggregation or {}).get(var, config.annual_how(var))
        ann = annual_series(m, min_months, how) if not m.empty else pd.Series(dtype=float)
        mk = engine.mann_kendall(ann, alpha, autocorrelation)
        smk = engine.seasonal_mann_kendall(m, alpha) if not m.empty else engine._result("no valid data")
        valid_years = ann.dropna().index
        rows.append({
            "location": loc, "variable": var, "unit": g["unit"].iat[0], "statistic": g["statistic"].iat[0],
            "latitude": g["latitude"].iat[0], "longitude": g["longitude"].iat[0],
            "source": g["source"].iat[0], "data_kind": g["data_kind"].iat[0],
            "annual_statistic": how, "fdr_family": families.get(var, config.PRIMARY_FAMILY),
            "n_years": mk["n"], "n_years_span": mk["n_span"], "year_coverage": mk["coverage"],
            "first_year_nominal": int(ann.index.min()) if len(ann) else np.nan,
            "last_year_nominal": int(ann.index.max()) if len(ann) else np.nan,
            "first_year": int(valid_years.min()) if len(valid_years) else np.nan,
            "last_year": int(valid_years.max()) if len(valid_years) else np.nan,
            "mk_trend": mk["trend"], "mk_p": mk["p"], "mk_z": mk["z"], "kendall_tau": mk["tau"],
            "variance_factor": mk["variance_factor"], "autocorrelation_method": autocorrelation, "lag1_autocorrelation": mk["rho1"],
            "sen_ci_low_per_decade": mk["slope_ci_low"] * 10, "sen_ci_high_per_decade": mk["slope_ci_high"] * 10,
            "mk_reason": mk["reason"],
            "sen_per_decade": engine.sens_slope_per_decade(ann),
            "seasonal_trend": smk["trend"], "seasonal_p": smk["p"],
            "seasonal_sen_per_decade": smk["slope"] * 10 if smk["slope"] == smk["slope"] else np.nan,
            "seasonal_reason": smk["reason"],
        })
        if not m.empty:
            a = engine.climatology_anomalies(m, base=base)
            a["qc_flag"] = g.set_index("date")["qc_flag"].reindex(a.index).fillna("absent")
            a.insert(0, "variable", var)
            a.insert(0, "location", loc)
            anoms.append(a.reset_index(names="date"))
    t = pd.DataFrame(rows)
    if t.empty:
        return t, pd.DataFrame()
    t["mk_p_fdr"] = np.nan
    t["seasonal_p_fdr"] = np.nan
    t["n_tests_in_family"] = 0
    for fam, idx in t.groupby("fdr_family").groups.items():
        t.loc[idx, "mk_p_fdr"] = engine.fdr_adjust(t.loc[idx, "mk_p"].values, alpha, fdr_method)
        t.loc[idx, "seasonal_p_fdr"] = engine.fdr_adjust(t.loc[idx, "seasonal_p"].values, alpha, fdr_method)
        t.loc[idx, "n_tests_in_family"] = int(t.loc[idx, "mk_p"].notna().sum())
    t["significant_uncorrected"] = t["mk_p"] < alpha
    t["significant_fdr"] = t["mk_p_fdr"] < alpha
    # descriptive slope is always shown; this column says how far the evidence goes
    t["evidence_class"] = np.select(
        [t["mk_trend"] == "insufficient_data", t["significant_fdr"], t["significant_uncorrected"]],
        ["insufficient_data", "significant_after_fdr", "significant_before_fdr_only"], default="not_significant")
    return t, (pd.concat(anoms, ignore_index=True) if anoms else pd.DataFrame())
