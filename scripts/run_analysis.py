"""Quality control tables, trend analysis, sensitivity runs and comparison tables for the processed data.

    python scripts/run_analysis.py [--out-dir reports]

Reads data/processed/power_monthly_standardised.csv. Refuses synthetic test data (unless --allow-synthetic,
used only by the test suite). Writes CSV tables to <out-dir>/tables and analysis_run.json. Nothing is
interpolated, filled or removed: flagged values stay NaN at their calendar position.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import datetime as dt
import hashlib
import json
import platform

import numpy as np
import pandas as pd
import scipy
import statsmodels

from earthscope import config
from earthscope.ingest import pipeline
from earthscope.qc import checks, diagnostics
from earthscope.trends import engine
from earthscope.trends.pipeline import annual_series, monthly_series, run_trends


def month_ranges(dates):
    """Compress a sorted list of month starts into 'YYYY-MM..YYYY-MM' ranges."""
    d = sorted(pd.DatetimeIndex(dates))
    if not d:
        return ""
    out, start, prev = [], d[0], d[0]
    for x in d[1:]:
        if (x.year * 12 + x.month) - (prev.year * 12 + prev.month) != 1:
            out.append((start, prev)); start = x
        prev = x
    out.append((start, prev))
    return "; ".join(f"{a:%Y-%m}" if a == b else f"{a:%Y-%m}..{b:%Y-%m}" for a, b in out)


def qc_tables(df, meta, preimport):
    cov, desc, susp, homog, flagged = [], [], [], [], []
    gaps = checks.gaps(df).set_index(["location", "variable"])["absent_months"]
    for (loc, var), g in df.groupby(["location", "variable"]):
        g = g.sort_values("date")
        ok = g[g.qc_flag == "ok"]
        miss = g[g.qc_flag == "missing"]
        cov.append({"location": loc, "variable": var, "unit": g.unit.iat[0], "statistic": g.statistic.iat[0],
                    "first_month_present": g.date.min().strftime("%Y-%m"), "last_month_present": g.date.max().strftime("%Y-%m"),
                    "n_months_present": len(g), "n_valid": len(ok), "n_missing_flagged": len(miss),
                    "n_out_of_range_flagged": int((g.qc_flag == "out_of_range").sum()),
                    "n_months_absent_inside_span": int(gaps.loc[(loc, var)]),
                    "pct_valid": round(100 * len(ok) / len(g), 2),
                    "first_valid_month": ok.date.min().strftime("%Y-%m") if len(ok) else "",
                    "last_valid_month": ok.date.max().strftime("%Y-%m") if len(ok) else "",
                    "missing_month_ranges": month_ranges(miss.date), "duplicate_records_in_processed": int(g.duplicated("date").sum())})
        v = ok.value
        desc.append({"location": loc, "variable": var, "unit": g.unit.iat[0], "mean": v.mean(), "sd": v.std(), "min": v.min(),
                     "date_of_min": ok.loc[v.idxmin(), "date"].strftime("%Y-%m"), "max": v.max(),
                     "date_of_max": ok.loc[v.idxmax(), "date"].strftime("%Y-%m")})
        m = monthly_series(g)
        summary, big = diagnostics.suspicious_months(m)
        susp.append({"location": loc, "variable": var, "n_out_of_range": int((g.qc_flag == "out_of_range").sum()), **summary})
        for d, r in big.iterrows():
            flagged.append({"location": loc, "variable": var, "date": d.strftime("%Y-%m"), "value": r.value,
                            "anomaly": r.anomaly, "z": r.z, "level": r.level})
        how = config.annual_how(var)
        ann = annual_series(m, how=how)
        ph, pd_ = diagnostics.pettitt(ann), diagnostics.pettitt_detrended(ann)
        homog.append({"location": loc, "variable": var, "annual_statistic": how, "n": ph["n"],
                      "raw_change_year": ph["change_year"], "raw_p": ph["p"], "raw_step": ph["step"], "raw_detected": ph["detected"],
                      "detrended_change_year": pd_["change_year"], "detrended_p": pd_["p"], "detrended_step": pd_["step"],
                      "detrended_detected": pd_["detected"]})
    dupes = []
    pre = {f["file"]: f for f in (preimport or {}).get("files", [])}
    for r in meta["files"]:
        orig = (r.get("import_record") or {}).get("original_filename", r["name"])
        chk = next((c for c in pre.get(orig, {}).get("checks", []) if c["check"] == "no_duplicate_keys"), None)
        dupes.append({"location": r["location"], "raw_file": orig, "duplicate_keys_in_raw_json": chk["status"] if chk else "not checked",
                      "duplicates_removed_when_merging": meta["duplicates_removed"],
                      "duplicate_location_variable_date_rows_in_processed": int(df[df.location == r["location"]].duplicated(["variable", "date"]).sum())})
    fl = pd.DataFrame(flagged)
    if len(fl):
        fl = fl.reindex(fl.z.abs().sort_values(ascending=False).index)
    return (pd.DataFrame(cov), pd.DataFrame(desc), pd.DataFrame(susp), fl, pd.DataFrame(homog), pd.DataFrame(dupes))


PRECIP_EXCLUDE_MM_PER_DAY = 5.0
SCENARIO_APPLIES_TO = {"T2M_MAX/MIN as annual mean of monthly extremes": ("T2M_MAX", "T2M_MIN"),
                       f"PRECTOTCORR without months more than {PRECIP_EXCLUDE_MM_PER_DAY:g} mm/day above the calendar-month mean": ("PRECTOTCORR",)}


def exclude_extreme_precip(df, threshold=PRECIP_EXCLUDE_MM_PER_DAY):
    """SENSITIVITY ONLY. Marks PRECTOTCORR months whose anomaly exceeds threshold as excluded, so that annual values
    containing them drop out. The primary analysis keeps every month."""
    d = df.copy()
    for loc, g in d[d.variable == "PRECTOTCORR"].groupby("location"):
        a = engine.climatology_anomalies(monthly_series(g))
        bad = a.index[a["anomaly"] > threshold]
        d.loc[(d.location == loc) & (d.variable == "PRECTOTCORR") & d.date.isin(bad), "qc_flag"] = "sensitivity_excluded"
    return d


def scenarios(df):
    """Primary analysis plus sensitivity runs. Returns (primary_trends, anomalies, long table of all scenarios)."""
    runs = {
        "primary (ar1_neff, BH, annual extremes for T2M_MAX/MIN, 1981-2025)": dict(),
        "no autocorrelation correction": dict(autocorrelation="none"),
        "Hamed-Rao correction": dict(autocorrelation="hamed_rao"),
        "Benjamini-Yekutieli FDR": dict(fdr_method="by"),
        "T2M_MAX/MIN as annual mean of monthly extremes": dict(aggregation={"T2M_MAX": "day_weighted_mean", "T2M_MIN": "day_weighted_mean"}),
        "common period 1984-2025": dict(_filter=True),
        f"PRECTOTCORR without months more than {PRECIP_EXCLUDE_MM_PER_DAY:g} mm/day above the calendar-month mean": dict(_precip=True),
    }
    rows, primary, anoms = [], None, None
    for name, kw in runs.items():
        kw = dict(kw)
        use = df[df.date >= "1984-01-01"] if kw.pop("_filter", False) else df
        if kw.pop("_precip", False):
            use = exclude_extreme_precip(df)
        t, a = run_trends(use, **kw)
        if primary is None:
            primary, anoms = t, a
        keep = ["location", "variable", "fdr_family", "annual_statistic", "n_years", "n_years_span", "sen_per_decade", "mk_p", "mk_p_fdr",
                "significant_uncorrected", "significant_fdr", "evidence_class", "variance_factor", "mk_reason"]
        rows.append(t[keep].assign(scenario=name))
    return primary, anoms, pd.concat(rows, ignore_index=True)


def robustness(long):
    base_name = long.scenario.iat[0]
    base = long[long.scenario == base_name].set_index(["location", "variable"])
    out = []
    for (loc, var), b in base.iterrows():
        sub = long[(long.location == loc) & (long.variable == var) & (long.scenario != base_name)]
        sub = sub[[var in SCENARIO_APPLIES_TO.get(sc, (var,)) for sc in sub.scenario]]
        same = sub[sub.evidence_class == b.evidence_class]
        signs = np.sign(sub.sen_per_decade.dropna())
        out.append({"location": loc, "variable": var, "primary_evidence_class": b.evidence_class, "n_sensitivity_runs": len(sub),
                    "n_same_evidence_class": len(same), "same_sign_of_slope_in_all_runs": bool(len(signs) and (signs == np.sign(b.sen_per_decade)).all()),
                    "range_of_slope_per_decade": (f"{sub.sen_per_decade.min():.4f} to {sub.sen_per_decade.max():.4f}" if sub.sen_per_decade.notna().any() else ""),
                    "differing_runs": "; ".join(sub[sub.evidence_class != b.evidence_class].scenario)})
    return pd.DataFrame(out)


def comparison_tables(df, trends):
    clim = []
    for (loc, var), g in df.groupby(["location", "variable"]):
        m = monthly_series(g)
        how = config.annual_how(var)
        ann = annual_series(m, how=how)
        sel = ann[(ann.index >= 1991) & (ann.index <= 2020)].dropna()
        clim.append({"location": loc, "variable": var, "unit": g.unit.iat[0], "annual_statistic": how,
                     "mean_1991_2020": sel.mean(), "sd_between_years": sel.std(), "n_years": len(sel)})
    clim = pd.DataFrame(clim)
    wide = {}
    for col, label in (("mean_1991_2020", "mean_1991_2020"),):
        wide[label] = clim.pivot(index="variable", columns="location", values=col).round(3)
    t = trends.copy()
    t["cell"] = t.apply(lambda r: "n/a" if pd.isna(r.sen_per_decade) else
                        f"{r.sen_per_decade:+.3f} [{r.sen_ci_low_per_decade:+.3f}, {r.sen_ci_high_per_decade:+.3f}]", axis=1)
    wide["sen_slope_per_decade_with_95pct_interval"] = t.pivot(index="variable", columns="location", values="cell")
    wide["evidence_class"] = t.pivot(index="variable", columns="location", values="evidence_class")
    wide["p_uncorrected"] = t.pivot(index="variable", columns="location", values="mk_p").round(4)
    wide["p_fdr_within_family"] = t.pivot(index="variable", columns="location", values="mk_p_fdr").round(4)
    return clim, wide


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(config.ROOT / "reports"))
    ap.add_argument("--allow-synthetic", action="store_true")
    args = ap.parse_args(argv)
    src = config.processed_dir() / pipeline.PROCESSED_NAME
    if not src.exists():
        print(f"[FAIL] {src} not found. Import data first.")
        return 1
    df = pd.read_csv(src, parse_dates=["date"])
    if (df.source == "SYNTHETIC TEST DATA").any() and not args.allow_synthetic:
        print("[FAIL] the processed data contains SYNTHETIC TEST DATA. Refusing to analyse it.")
        return 1
    meta = json.loads((config.processed_dir() / pipeline.METADATA_NAME).read_text())
    pre_path = Path(args.out_dir) / "preimport_validation.json"
    preimport = json.loads(pre_path.read_text()) if pre_path.exists() else None
    out = Path(args.out_dir) / "tables"
    out.mkdir(parents=True, exist_ok=True)

    cov, desc, susp, flagged, homog, dupes = qc_tables(df, meta, preimport)
    primary, anoms, long = scenarios(df)
    rob = robustness(long)
    clim, wide = comparison_tables(df, primary)

    for name, tab in {"qc_coverage_missingness": cov, "qc_descriptive_statistics": desc, "qc_suspicious_value_summary": susp,
                      "qc_flagged_months_abs_z_ge_3": flagged, "qc_homogeneity_pettitt": homog, "qc_duplicates": dupes,
                      "trend_results_primary": primary, "sensitivity_all_scenarios": long, "sensitivity_robustness": rob,
                      "climatology_1991_2020": clim}.items():
        tab.to_csv(out / f"{name}.csv", index=False)
    for name, tab in wide.items():
        tab.to_csv(out / f"compare_{name}.csv")
    primary.to_csv(config.processed_dir() / "trend_results.csv", index=False)
    anoms.to_csv(config.processed_dir() / "anomalies.csv", index=False)
    run = {"run_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "input_file": src.name, "input_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "rows": int(len(df)),
           "versions": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
                        "statsmodels": statsmodels.__version__},
           "parameters": {"alpha": 0.05, "autocorrelation": "ar1_neff", "fdr_method": "bh", "fdr_families": config.FDR_FAMILIES,
                          "annual_aggregation": {"default": "day_weighted_mean", **config.ANNUAL_AGGREGATION},
                          "min_valid_years": engine.MIN_VALID_YEARS, "min_year_coverage": engine.MIN_YEAR_COVERAGE,
                          "min_years_per_month": engine.MIN_YEARS_PER_MONTH, "min_base_years": engine.MIN_BASE_YEARS,
                          "min_months_per_year": 12, "anomaly_base_period": [1991, 2020]},
           "scenarios": list(long.scenario.unique()), "synthetic_data": bool((df.source == "SYNTHETIC TEST DATA").any())}
    (Path(args.out_dir) / "analysis_run.json").write_text(json.dumps(run, indent=2))
    print(f"{len(primary)} series analysed; evidence classes: {primary.evidence_class.value_counts().to_dict()}")
    print(f"tables written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
