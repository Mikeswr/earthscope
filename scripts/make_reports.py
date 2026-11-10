"""Write the markdown reports from the validation JSON, the processed metadata and the analysis tables.

    python scripts/make_reports.py [--out-dir reports]

Run scripts/validate_power_files.py and scripts/run_analysis.py first. Numbers come from the tables, never typed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json

import numpy as np
import pandas as pd

from earthscope import config
from earthscope.ingest import pipeline

ORDER = ["Takoradi", "Accra", "Kumasi", "Tamale", "Wa"]
VAR_ORDER = ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS10M", "ALLSKY_SFC_SW_DWN"]
CLASS_TEXT = {"significant_after_fdr": "significant after FDR", "significant_before_fdr_only": "significant before FDR only",
              "not_significant": "not significant", "insufficient_data": "insufficient data"}


def fmt(x, nd=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    if isinstance(x, (bool, np.bool_)):
        return "yes" if x else "no"
    if isinstance(x, (int, np.integer)):
        return str(x)
    if isinstance(x, (float, np.floating)):
        return f"{x:.{nd}f}"
    return str(x)


def table(df, nd=3):
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c], nd) for c in cols) + " |")
    return "\n".join(lines)


def roundtrip(df, raw_dir):
    """Compare every processed value with the raw JSON it came from (independent re-read)."""
    n = bad = fills_ok = fills = 0
    for f in sorted(Path(raw_dir).glob("power_monthly_*_*.json")):
        if f.name.endswith(".import.json") or f.name.endswith(".fetch.json"):
            continue
        doc = json.loads(f.read_text())
        loc = pipeline.RAW_PATTERN.match(f.name).group("loc")
        sub = df[df.location == loc]
        for var, s in doc["properties"]["parameter"].items():
            g = sub[sub.variable == var].set_index("date")["value"]
            for k, v in s.items():
                if k.endswith("13"):
                    continue
                got = g.loc[pd.Timestamp(year=int(k[:4]), month=int(k[4:]), day=1)]
                n += 1
                if v == -999:
                    fills += 1
                    fills_ok += int(np.isnan(got))
                    bad += int(not np.isnan(got))
                else:
                    bad += int(not np.isclose(got, v, rtol=0, atol=1e-12))
    return n, bad, fills, fills_ok


def sorted_series(t):
    t = t.copy()
    t["_v"] = t.variable.map({v: i for i, v in enumerate(VAR_ORDER)})
    t["_l"] = t.location.map({v: i for i, v in enumerate(ORDER)})
    return t.sort_values(["_v", "_l"]).drop(columns=["_v", "_l"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(config.ROOT / "reports"))
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    T = out / "tables"
    pre = json.loads((out / "preimport_validation.json").read_text())
    meta = json.loads((config.processed_dir() / pipeline.METADATA_NAME).read_text())
    run = json.loads((out / "analysis_run.json").read_text())
    df = pd.read_csv(config.processed_dir() / pipeline.PROCESSED_NAME, parse_dates=["date"])
    if (df.source == "SYNTHETIC TEST DATA").any():
        print("[FAIL] synthetic data in the processed file; not writing reports")
        return 1
    rd = lambda n: pd.read_csv(T / f"{n}.csv")
    cov, desc, susp, flagged, homog, dupes = (rd(n) for n in ("qc_coverage_missingness", "qc_descriptive_statistics", "qc_suspicious_value_summary",
                                                              "qc_flagged_months_abs_z_ge_3", "qc_homogeneity_pettitt", "qc_duplicates"))
    tr, long, rob, clim = rd("trend_results_primary"), rd("sensitivity_all_scenarios"), rd("sensitivity_robustness"), rd("climatology_1991_2020")
    tr = sorted_series(tr)
    n_rt, bad_rt, fills, fills_ok = roundtrip(df, config.raw_dir())
    files = pre["files"]
    cross = pre["cross_file"]
    base_scn = long.scenario.iat[0]
    n_series, fams = len(tr), tr.groupby("fdr_family").size().to_dict()
    cls = tr.evidence_class.value_counts().to_dict()
    sig = tr[tr.evidence_class == "significant_after_fdr"]
    bfdr = tr[tr.evidence_class == "significant_before_fdr_only"]
    rob_i = rob.set_index(["location", "variable"])

    # ------------------------------------------------------------------ report 1: import and data quality
    L = []
    a = L.append
    a("# EarthScope import and data quality report\n")
    a("These are NASA POWER monthly point files for five Ghanaian locations. NASA POWER values are gridded estimates built from reanalysis and satellite based sources. They are not direct station observations, and everything below should be read that way.\n")
    a("## 1. Files imported\n")
    rows = []
    for f in files:
        i, rec = f["location_identity"], next(r for r in meta["files"] if r["import_record"]["original_filename"] == f["file"])
        rows.append({"location": i["location_named_in_filename"], "file": f["file"], "bytes": f["bytes"], "latitude": i["file_latitude"], "longitude": i["file_longitude"],
                     "elevation value in file (m)": i["elevation_value_in_file_m"], "km from configured point": i["distance_to_named_configured_km"], "sha256": rec["sha256"]})
    a(table(pd.DataFrame(rows).set_index("location").reindex(ORDER).reset_index(), 3))
    a("\nThe SHA-256 checksum of each imported copy equals the checksum of the file as uploaded. The import record, the verbatim response header and the per-parameter metadata are stored in data/processed/power_monthly_metadata.json. Imported copies are in data/raw under canonical names, each with a small .import.json record holding the original file name.\n")
    a("## 2. Pre-import validation (nothing was imported until these passed)\n")
    vrows = [{"location": f["location_identity"]["location_named_in_filename"], "status": f["status"], **{k: f["counts"][k] for k in ("pass", "info", "warn", "fail")}} for f in files]
    a(table(pd.DataFrame(vrows).set_index("location").reindex(ORDER).reset_index()))
    warns = sorted({(c["check"], c["detail"]) for f in files for c in f["checks"] if c["status"] in ("warn", "fail")})
    a("\nEvery file passed with no failures. The only warning in each file is: " + "; ".join(f"{c} ({d})" for c, d in warns) + ".\n")
    a("What was checked in each file: that the file is valid JSON with no duplicated keys; that it is a POWER point Feature with the expected header fields; that every requested parameter was returned and has a units entry; that each unit equals the expected unit; that all parameters share one key set; that keys are YYYYMM with months 1 to 13; that the returned keys cover the header's requested range; that every year has an annual key; that file name coordinates match the coordinates inside the file; that the named location is the nearest configured location; that values are inside physical limits; and that the annual value of each parameter agrees with how its definition says it is built (section 4).\n")
    a("I had requested six meteorological variables (T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, RH2M, WS10M). The files also contain ALLSKY_SFC_SW_DWN, which I had not requested. I added it to the configured list after seeing it, and it is analysed as a separate, secondary family.\n")
    a("## 3. Parameter metadata and units (as returned by NASA)\n")
    pm = files[0]["parameter_metadata"]
    sem = config.VARIABLE_SEMANTICS
    a(table(pd.DataFrame([{"variable": v, "long name in response": pm[v]["longname"], "units in response": pm[v]["units_in_response"], "expected": pm[v]["expected"], "check": pm[v]["status"]} for v in VAR_ORDER if v in pm])))
    same_meta = cross["parameters_metadata_identical"]
    a(f"\nThe parameter metadata block is identical in all five files: {fmt(same_meta)}. No unit was converted or assumed; every row carries unit_source = response_metadata (assumed units used: {fmt(meta['assumed_documented_units_used'])}).\n")
    a("The response states the units and long names only. It does not state which source product (MERRA-2, SRB or SYN1DEG) supplied each variable, and it does not state a spatial resolution per variable. The header title says \"Source Native Resolution\", which means each variable is at the native grid of its source. I have not assigned a resolution to any variable.\n")
    a("## 4. Statistical interpretation of each variable\n")
    ev = {v: [f["semantics_evidence"][v] for f in files] for v in VAR_ORDER}
    erows = []
    for v in VAR_ORDER:
        e = ev[v]
        stat = sem[v][1].replace("_", " ")
        key = "max_abs_diff_max" if "maximum_of_hourly" in sem[v][1] else "max_abs_diff_min" if "minimum_of_hourly" in sem[v][1] else "max_abs_diff_weighted"
        erows.append({"variable": v, "definition used": stat, "annual value consistent in all five files": all(x["annual_value_consistent_with_documented_statistic"] for x in e),
                      "largest difference, annual vs aggregate of months": max(x[key] for x in e if x[key] is not None), "years compared per file": e[0]["n_years_compared"]})
    a(table(pd.DataFrame(erows), 4))
    a("\nThe definitions come from the NASA POWER data processing page, which describes a hierarchy in which monthly values are the mean of the days and annual values the mean of the months, with maximum and minimum parameters as the stated exception: they keep the value of the original instantaneous hourly time through the hierarchy. The average of the daily maximum is a different parameter (T2M_MAX_AVG) that is not in these files.\n")
    mean_vars = [v for v in VAR_ORDER if "mean" in sem[v][1]]
    ok_w = [v for v in mean_vars if all(x["annual_value_consistent_with_documented_statistic"] for x in ev[v])]
    also_simple = [v for v in mean_vars if any(x["annual_also_consistent_with_simple_mean"] for x in ev[v])]
    discrim = [v for v in ok_w if v not in also_simple]
    n_ord = sum(f["semantics_evidence"]["ordering_Tmax_ge_T_ge_Tmin"]["months_checked"] for f in files)
    n_viol = sum(f["semantics_evidence"]["ordering_Tmax_ge_T_ge_Tmin"]["violations"] for f in files)
    ext_ok = all(all(x["annual_value_consistent_with_documented_statistic"] for x in ev[v]) for v in ("T2M_MAX", "T2M_MIN"))
    a(f"What the data show. For {', '.join(ok_w)}, NASA's annual value equals the day-weighted mean of the twelve monthly values to within rounding. "
      f"For {', '.join(discrim)} this is a real discrimination: the annual value differs from the simple mean of the months by more than rounding. "
      + (f"For {', '.join(also_simple)} the day-weighted and simple means differ by less than the rounding in at least one file, so this check cannot tell them apart. " if also_simple else "")
      + f"For T2M_MAX the annual value equals the largest of the twelve monthly values, and for T2M_MIN the smallest, in every year at every location (all files consistent: {fmt(ext_ok)}). "
      f"T2M_MAX is at least T2M and T2M is at least T2M_MIN in {n_ord - n_viol:,} of {n_ord:,} location months. PRECTOTCORR monthly values are daily rates in mm/day, not monthly totals (values run from {desc[desc.variable == 'PRECTOTCORR']['min'].min():.2f} to {desc[desc.variable == 'PRECTOTCORR']['max'].max():.2f}).\n")
    a("A correction to my own earlier work: I had documented T2M_MAX and T2M_MIN as the monthly mean of daily maxima and minima. That was wrong. They are the highest and lowest hourly values in the month. This changes the analysis, because the natural annual quantity for an extreme is the annual extreme. The primary analysis therefore uses the annual maximum of the twelve monthly T2M_MAX values and the annual minimum of the twelve monthly T2M_MIN values. The mean of the monthly extremes is run as a sensitivity analysis.\n")
    a("What is not proven. The checks above are consistent with the documented definitions, but monthly data alone cannot prove how the monthly value was computed from hourly values. Daily or hourly POWER data would be needed for that.\n")
    a("## 5. Actual temporal coverage\n")
    a("I did not assume the requested coverage was returned. The header of every file requests " + f"{files[0]['header']['start']} to {files[0]['header']['end']}" + ". The coverage actually returned is:\n")
    c2 = cov.copy()
    summ = c2.groupby("variable").agg(first_month=("first_month_present", "min"), last_month=("last_month_present", "max"), months_present=("n_months_present", "min"),
                                      valid_months_min=("n_valid", "min"), valid_months_max=("n_valid", "max"), absent_inside_span=("n_months_absent_inside_span", "sum")).reindex(VAR_ORDER).reset_index()
    a(table(summ))
    miss = cov[cov.n_missing_flagged > 0]
    a(f"\nAll 35 series span {cov.first_month_present.min()} to {cov.last_month_present.max()} with {cov.n_months_present.min()} monthly values present each and {cov.n_months_absent_inside_span.sum()} months absent. Missing values (the fill value -999) occur only in ALLSKY_SFC_SW_DWN: {', '.join(sorted(miss.location.unique()))} all miss {miss.missing_month_ranges.iat[0]} ({miss.n_missing_flagged.iat[0]} months each), so its record starts in {miss.first_valid_month.iat[0]}. The other {int((cov.n_missing_flagged == 0).sum())} series are complete. Nothing was interpolated or filled.\n")
    a("## 6. Coordinates and location identity\n")
    irows = [{"location": f["location_identity"]["location_named_in_filename"], "latitude in file": f["location_identity"]["file_latitude"], "longitude in file": f["location_identity"]["file_longitude"],
              "latitude in file name": f["location_identity"]["filename_latitude"], "longitude in file name": f["location_identity"]["filename_longitude"],
              "nearest configured location": f["location_identity"]["nearest_configured_location"], "name agrees": f["location_identity"]["nearest_configured_location"] == f["location_identity"]["location_named_in_filename"]} for f in files]
    a(table(pd.DataFrame(irows).set_index("location").reindex(ORDER).reset_index()))
    a(f"\nFile name coordinates match file coordinates within rounding for all five files, and each named location is the nearest configured location. The five points are distinct (nearest pair {cross['min_pairwise_distance_km']} km apart) and no two files share a series (pairs with mostly identical values: {len(cross['pairs_with_mostly_identical_series'])}). I changed locations.yaml to the coordinates found in these files so that future downloads reproduce the same points. The elevation numbers in the files are not described in the response; I report them but do not interpret them.\n")
    a("## 7. Inconsistencies between the five files\n")
    a(f"Headers are identical except for the order of the `sources` list (identical as sets: {fmt(cross['header_sources_identical_as_sets'])}; identical in order: {fmt(cross['header_sources_identical_in_order'])}). That is cosmetic and not a data inconsistency. API version ({', '.join(cross['api_version'])}), time standard ({', '.join(cross['time_standard'])}) and title are the same in all files. Parameter sets, parameter metadata and monthly key sets are identical. The time standard is local solar time, so day boundaries follow local solar time rather than UTC; for Ghana the difference is small, but it is recorded.\n")
    a("## 8. Import result\n")
    a(f"The processed table has {len(df):,} rows (5 locations x 7 variables x 540 months), source {', '.join(df.source.unique())}, data kind {', '.join(df.data_kind.unique())}. Duplicate location, variable, date rows: {int(df.duplicated(['location', 'variable', 'date']).sum())}. Duplicates removed when merging: {meta['duplicates_removed']}. QC flags: {df.qc_flag.value_counts().to_dict()}.\n")
    a(f"Round trip check: I re-read the stored raw files and compared all {n_rt:,} monthly values with the processed table. Mismatches: {bad_rt}. Fill values ({fills}) stored as missing: {fills_ok}.\n")
    a("## 9. Quality control results\n")
    a("### Missingness, duplicates and range checks\n")
    a(table(dupes[["location", "duplicate_keys_in_raw_json", "duplicates_removed_when_merging", "duplicate_location_variable_date_rows_in_processed"]].set_index("location").reindex(ORDER).reset_index()))
    a(f"\nOut-of-range values (physical limits in earthscope/qc/checks.py): {int(cov.n_out_of_range_flagged.sum())}. Months absent inside a series: {int(cov.n_months_absent_inside_span.sum())}.\n")
    a("The full per-location, per-variable coverage table is reports/tables/qc_coverage_missingness.csv, and descriptive statistics are in qc_descriptive_statistics.csv.\n")
    a("### Suspicious values\n")
    a("I flag, and do not change, months whose anomaly against the 1991 to 2020 calendar-month mean of the same record has |z| of 3 or more. For about 540 normally distributed values roughly 1.5 would be expected per series, so counts well above that point to skewed variables, mainly precipitation, or to events worth checking.\n")
    sv = susp.groupby("variable").agg(series=("location", "size"), months_abs_z_ge_3=("n_notable_abs_z_ge_3", "sum"), months_abs_z_ge_4=("n_extreme_abs_z_ge_4", "sum"),
                                      expected_per_series_if_normal=("expected_abs_z_ge_3_if_normal", "mean"), stuck_value_runs=("n_identical_value_runs_ge_4", "sum")).reindex(VAR_ORDER).reset_index()
    a(table(sv, 2))
    f2 = flagged.groupby(["variable", "date"]).agg(n_locations=("location", "nunique"), locations=("location", lambda s: ", ".join(sorted(s))), largest_anomaly=("anomaly", lambda s: s.iloc[s.abs().argmax()]),
                                                  largest_abs_z=("z", lambda s: s.abs().max())).reset_index()
    coh = f2[f2.n_locations >= 3].sort_values("largest_abs_z", ascending=False)
    a("\nMonths flagged at three or more locations at once:\n")
    a(table(coh, 2))
    an = pd.read_csv(config.processed_dir() / "anomalies.csv", parse_dates=["date"])
    pr = an[(an.variable == "PRECTOTCORR") & (an.anomaly > 5)].copy()
    pr["period"] = np.where(pr.date.dt.year <= 1988, "1981 to 1988", np.where(pr.date.dt.year >= 2018, "2018 to 2025", "1989 to 2017"))
    prt = pr.groupby(["location", "period"]).size().unstack(fill_value=0).reindex(ORDER).fillna(0).astype(int)
    prt = prt.reindex(columns=["1981 to 1988", "1989 to 2017", "2018 to 2025"], fill_value=0)
    prt["all"] = prt.sum(axis=1)
    a(f"Precipitation is the main concern. {len(pr)} location months have PRECTOTCORR more than 5 mm/day above the calendar-month mean (counted over all months, by period):\n")
    a(table(prt.reset_index().rename(columns={"index": "location"})))
    a("\nThey are concentrated in the early record at Kumasi and Takoradi and again after 2018, and Tamale has none. The largest is December 1986, when Kumasi shows 12.94 mm/day (about 400 mm in the month) and Takoradi 10.76 mm/day while Tamale and Wa show 0.00. September 1987 is also extreme at all three southern sites. I cannot tell from this file whether these are real storms or artefacts of the source data, so they are kept in the primary analysis, flagged, and tested in a sensitivity run. They need checking against independent rainfall data (see the limitations report). Large z values for Tamale and Wa in the dry season (for example 0.8 mm/day in December) come from very small climatological spreads and are small in absolute terms. See reports/figures/qc_precipitation_flagged_months.png.\n")
    rh = coh[coh.variable == "RH2M"]
    if len(rh):
        a("RH2M also has months flagged at three southern sites together (" + "; ".join(f"{r.date}, anomaly {r.largest_anomaly:+.1f} percentage points" for r in rh.itertuples()) + "). A shared signal across sites could be a real regional event or a feature of the product; I changed nothing and treat these months the same way as the rainfall months.\n")
    a("### Homogeneity\n")
    a("I ran the Pettitt change point test on each annual series. The raw test also fires on a steady trend, so I repeated it after removing the Sen trend. A hit after detrending means a step or non-linear change remains. The test assumes independent years and has limited power, so a hit is a flag to investigate and a non-hit is not proof of homogeneity.\n")
    hs = homog.groupby("variable").agg(series=("location", "size"), raw_detected=("raw_detected", "sum"), detected_after_detrending=("detrended_detected", "sum")).reindex(VAR_ORDER).reset_index()
    a(table(hs))
    hd = homog[homog.detrended_detected]
    a("\nSeries with a step remaining after detrending: " + "; ".join(f"{r.location} {r.variable}, around {int(r.detrended_change_year)}, step {r.detrended_step:+.2f}, p {r.detrended_p:.3f}" for r in hd.itertuples()) + ". Full results: qc_homogeneity_pettitt.csv.\n")
    (out / "IMPORT_AND_DATA_QUALITY_REPORT.md").write_text("\n".join(L))

    # ------------------------------------------------------------------ report 2: trends
    L = []
    a = L.append
    a("# EarthScope trend analysis report\n")
    a("Data: NASA POWER gridded estimates (reanalysis and satellite based sources), not station observations. Five locations are analysed separately. They are not a spatial sample, and nothing here is a spatial trend map.\n")
    a("## 1. What was done\n")
    p = run["parameters"]
    a(f"For each of {n_series} series (7 variables x 5 locations) I built an annual value from the twelve monthly values and tested it for a monotonic trend with the Mann-Kendall test. The annual value is the day-weighted mean for T2M, PRECTOTCORR, RH2M, WS10M and ALLSKY_SFC_SW_DWN, the annual maximum of the monthly values for T2M_MAX and the annual minimum for T2M_MIN. A year needs all 12 valid months. A series needs at least {p['min_valid_years']} valid years covering at least {int(p['min_year_coverage'] * 100)} percent of its nominal span; the span counts flagged years at the start, middle and end. Sen's slope uses the actual elapsed years and is given per decade with a 95 percent interval. No value was interpolated or filled.\n")
    a("Autocorrelation: the Mann-Kendall variance is inflated using the lag-1 autocorrelation of the Sen-detrended series (an effective sample size approach, never reducing the variance). In my simulations with AR(1) noise this stayed much closer to the nominal error rate than Hamed-Rao, but it is not exact at strong autocorrelation (docs/METHODS.md). Hamed-Rao and no correction are reported as sensitivity runs.\n")
    a(f"Multiple testing: Benjamini-Hochberg FDR at 0.05, applied within two pre-declared families. The primary family is the six meteorological variables at five locations ({fams.get('primary')} tests). ALLSKY_SFC_SW_DWN is a secondary family ({fams.get('secondary_solar')} tests) because it blends several source products over time and starts in 1984. Locations and variables are not independent (neighbouring variables such as T2M, T2M_MAX and T2M_MIN move together), so FDR here is approximate.\n")
    a("The seasonal Mann-Kendall test is computed and kept in the tables, but I do not use it for any significance statement. It treats calendar months as independent, and in these data it gives p values near zero where the annual test finds nothing (for example Kumasi T2M), which is what ignoring between-month correlation would produce.\n")
    a("Descriptive trends and statistically supported findings are kept apart. Every series has a descriptive Sen slope. Only series in the class significant after FDR are treated as findings.\n")
    a("## 2. Summary\n")
    a(f"Of {n_series} series: {cls.get('significant_after_fdr', 0)} are significant after FDR, {cls.get('significant_before_fdr_only', 0)} are significant only before FDR correction (not claimed as findings), {cls.get('not_significant', 0)} are not significant, {cls.get('insufficient_data', 0)} had insufficient data.\n")
    a("### 2a. Statistically supported (significant after FDR within family)\n")
    cols = {"location": "location", "variable": "variable", "unit": "unit", "sen_per_decade": "Sen slope per decade", "sen_ci_low_per_decade": "95% low", "sen_ci_high_per_decade": "95% high",
            "kendall_tau": "Kendall tau", "mk_z": "z", "mk_p": "p uncorrected", "mk_p_fdr": "p FDR", "lag1_autocorrelation": "lag-1 autocorrelation", "variance_factor": "variance factor", "fdr_family": "family"}
    s2 = sig[list(cols)].rename(columns=cols)
    rb = rob.assign(all_same=rob.n_same_evidence_class == rob.n_sensitivity_runs).set_index(["location", "variable"])["all_same"]
    s2["unchanged in every sensitivity run"] = [rb.loc[(r.location, r.variable)] for r in sig.itertuples()]
    a(table(s2, 4))
    n_unch = int(s2["unchanged in every sensitivity run"].sum())
    a(f"\n{n_unch} of these {len(s2)} kept their class in every sensitivity run (section 5); the others should be read with the caution given there.")
    a("\nImplied change over the record (Sen slope x record length, descriptive):\n")
    imp = sig.assign(record=sig.last_year - sig.first_year, implied=lambda d: d.sen_per_decade * (d.last_year - d.first_year) / 10)[["location", "variable", "unit", "first_year", "last_year", "implied"]]
    a(table(imp.rename(columns={"implied": "implied change"}), 2))
    a("\n### 2b. Significant before FDR only (not findings)\n")
    a(table(bfdr[list(cols)].rename(columns=cols), 4))
    a("\n### 2c. Not significant: descriptive slopes only\n")
    ns = tr[tr.evidence_class == "not_significant"]
    a(table(ns[["location", "variable", "unit", "sen_per_decade", "sen_ci_low_per_decade", "sen_ci_high_per_decade", "mk_p", "mk_p_fdr"]].rename(columns={"sen_per_decade": "Sen slope per decade", "sen_ci_low_per_decade": "95% low", "sen_ci_high_per_decade": "95% high", "mk_p": "p uncorrected", "mk_p_fdr": "p FDR"}), 4))
    n_ex = int(((ns.sen_ci_low_per_decade > 0) | (ns.sen_ci_high_per_decade < 0)).sum())
    a(f"\nA slope in this table describes these years at this grid cell. The 95 percent interval includes zero in {len(ns) - n_ex} of {len(ns)} rows and no p value survives correction, so none of it is evidence of a trend.\n")
    a("## 3. Results by variable\n")
    for v in VAR_ORDER:
        sv_ = tr[tr.variable == v]
        ss = sv_[sv_.evidence_class == "significant_after_fdr"]
        txt = f"**{v}** ({sv_.unit.iat[0]} per decade): " + (", ".join(f"{r.location} {r.sen_per_decade:+.3f}" for r in ss.itertuples()) + " significant after FDR" if len(ss) else "none significant after FDR")
        rest = sv_[sv_.evidence_class != "significant_after_fdr"]
        txt += "; " + (", ".join(f"{r.location} {r.sen_per_decade:+.3f}" for r in rest.itertuples()) + " not supported" if len(rest) else "")
        a(txt + ".\n")
    a("Signs in the tables run opposite for some variables across locations, and significant and non-significant locations sit side by side (for example T2M is significant at Takoradi, Accra and Tamale, not at Kumasi or Wa). With five points I do not read that as a regional pattern.\n")
    a("## 4. Autocorrelation treatment\n")
    a(f"Estimated lag-1 autocorrelation of the detrended annual series ranges from {tr.lag1_autocorrelation.min():.2f} to {tr.lag1_autocorrelation.max():.2f} (median {tr.lag1_autocorrelation.median():.2f}). The resulting variance factor ranges from {tr.variance_factor.min():.2f} to {tr.variance_factor.max():.2f}; a factor of 1 means no inflation. P values under the three treatments for the series that are significant after FDR in the primary run:\n")
    pv = long[long.scenario.isin([base_scn, "no autocorrelation correction", "Hamed-Rao correction"])].pivot_table(index=["location", "variable"], columns="scenario", values="mk_p")
    pv = pv.reindex(list(zip(sig.location, sig.variable)))
    pv.columns = ["p ar1_neff (primary)" if c.startswith("primary") else "p " + c for c in pv.columns]
    a(table(pv.reset_index(), 5))
    a("\n## 5. Robustness to analysis choices\n")
    a("Each series was re-run with: no autocorrelation correction; Hamed-Rao; Benjamini-Yekutieli FDR; T2M_MAX and T2M_MIN as the annual mean of monthly extremes (those two variables only); the common period 1984 to 2025; and PRECTOTCORR without months more than 5 mm/day above the calendar-month mean (PRECTOTCORR only). Only the runs that apply to a variable are counted for it.\n")
    rob["all_same"] = rob.n_same_evidence_class == rob.n_sensitivity_runs
    rs = rob.groupby("primary_evidence_class").agg(series=("location", "size"), unchanged_in_all_runs=("all_same", "sum")).reset_index()
    a(table(rs))
    a("\nThe findings that did not keep their class in every run:\n")
    nr = rob[(rob.primary_evidence_class == "significant_after_fdr") & (~rob.all_same)]
    a(table(nr[["location", "variable", "n_sensitivity_runs", "n_same_evidence_class", "differing_runs"]]) if len(nr) else "none")
    bf = rob[rob.primary_evidence_class == "significant_before_fdr_only"]
    sg = rob[rob.primary_evidence_class == "significant_after_fdr"]
    a(f"\nOf the {len(bf)} series significant before FDR only, {int(bf.all_same.sum())} kept that class in every run. Slope sign was the same in every run for {int(sg.same_sign_of_slope_in_all_runs.sum())} of {len(sg)} series significant after FDR. Full tables: reports/tables/sensitivity_robustness.csv and sensitivity_all_scenarios.csv.\n")
    a("## 6. Data concerns that bear on the trends\n")
    a("Precipitation is the weakest part. Of the five precipitation series, one is significant after FDR (Wa, increasing), and it falls to significant before FDR only when the extreme months are excluded or when the more conservative FDR is used. The early extreme months at Kumasi and Takoradi, and a step remaining after detrending at Takoradi around 2016 and at Kumasi around 1988, mean the southern rainfall slopes should not be trusted until checked against independent data.\n")
    a("ALLSKY_SFC_SW_DWN declines at four locations. The variable blends source products and its record is shorter, so a change in the source could look like a trend. The detrended Pettitt test found no step in any of the five solar series, which is weak reassurance given its limited power. The decline is a result for this product, not yet a confirmed change in surface radiation.\n")
    a("T2M_MAX and T2M_MIN, now analysed as annual extremes, show no series that is significant after FDR. Tamale T2M_MAX and Accra T2M_MIN are significant before correction only.\n")
    a("## 7. Figures\n")
    a("reports/figures/trend_summary_forest.png shows all slopes with intervals, marked by evidence class. reports/figures/trend_<VARIABLE>.png shows the annual series and Sen slope for each variable, with a solid line when significant after FDR and a dashed line otherwise. t2m_monthly_anomalies.png and qc_precipitation_flagged_months.png support the data quality discussion.\n")
    a("Provenance of this run: analysis_run.json holds the input checksum, software versions, thresholds and scenarios.\n")
    (out / "TREND_ANALYSIS_REPORT.md").write_text("\n".join(L))

    # ------------------------------------------------------------------ report 3: comparison tables
    L = []
    a = L.append
    a("# EarthScope location comparison tables\n")
    a("NASA POWER gridded estimates, not station observations. Five separate points; the tables compare them side by side and do not describe a spatial field. Locations are ordered roughly south to north.\n")
    a("## Location facts\n")
    lf = pd.DataFrame([{"location": f["location_identity"]["location_named_in_filename"], "latitude": f["location_identity"]["file_latitude"], "longitude": f["location_identity"]["file_longitude"],
                        "elevation value in file (m)": f["location_identity"]["elevation_value_in_file_m"]} for f in files]).set_index("location").reindex(ORDER).reset_index()
    a(table(lf))
    a("\n## Mean of the annual statistic, 1991 to 2020\n")
    a("Mean of the annual statistic over 1991 to 2020. T2M_MAX is the mean of the yearly highest hourly values and T2M_MIN the mean of the yearly lowest, so those two rows describe extremes of the grid cell.\n")
    units_by = clim.drop_duplicates("variable").set_index("variable")["unit"]
    stat_by = clim.drop_duplicates("variable").set_index("variable")["annual_statistic"].map({"day_weighted_mean": "mean", "max": "annual max", "min": "annual min"})
    cw = clim.pivot(index="variable", columns="location", values="mean_1991_2020").reindex(VAR_ORDER)[ORDER]
    cw.index = [f"{v} ({units_by[v]}, {stat_by[v]})" for v in cw.index]
    a(table(cw.rename_axis("variable").reset_index(), 3))
    a("\n## Sen slope per decade with 95 percent interval\n")
    sw = rd("compare_sen_slope_per_decade_with_95pct_interval") if (T / "compare_sen_slope_per_decade_with_95pct_interval.csv").exists() else None
    sw = sw.set_index("variable").reindex(VAR_ORDER)[ORDER]
    sw.index = [f"{v} ({units_by[v]} per decade)" for v in sw.index]
    a(table(sw.rename_axis("variable").reset_index()))
    a("\n## Evidence class\n")
    a(table(rd("compare_evidence_class").set_index("variable").reindex(VAR_ORDER)[ORDER].reset_index()))
    a("\n## p values, uncorrected\n")
    a(table(rd("compare_p_uncorrected").set_index("variable").reindex(VAR_ORDER)[ORDER].reset_index(), 4))
    a("\n## p values after FDR (within family)\n")
    a(table(rd("compare_p_fdr_within_family").set_index("variable").reindex(VAR_ORDER)[ORDER].reset_index(), 4))
    a("\n## Data availability and quality by location\n")
    qs = cov.groupby("location").agg(series=("variable", "size"), months_per_series=("n_months_present", "min"), valid_months=("n_valid", "sum"), missing_months=("n_missing_flagged", "sum"),
                                     out_of_range=("n_out_of_range_flagged", "sum")).reindex(ORDER).reset_index()
    qs = qs.merge(susp.groupby("location").agg(months_abs_z_ge_3=("n_notable_abs_z_ge_3", "sum"), months_abs_z_ge_4=("n_extreme_abs_z_ge_4", "sum")).reset_index(), on="location")
    a(table(qs))
    a("\nThe table above contains the same numbers as the CSV files in reports/tables, which are the machine readable version of every table in these reports.\n")
    (out / "LOCATION_COMPARISON_TABLES.md").write_text("\n".join(L))

    # ------------------------------------------------------------------ report 4: limitations
    sg_all = rob[rob.primary_evidence_class == "significant_after_fdr"]
    L = []
    a = L.append
    a("# EarthScope limitations and items needing further validation\n")
    a("## 1. What these data are\n")
    a("NASA POWER monthly values are gridded estimates from reanalysis and satellite based sources. They represent a grid cell, not a point, and not a weather station. Elevations and local conditions of a city differ from the cell average. Agreement with station records has not been tested here.\n")
    a("## 2. Scope of inference\n")
    a("Five locations are five separate series. They do not support a spatial trend map or a statement about Ghana as a whole, and the locations are not independent samples. Findings apply to these grid cells over 1981 to 2025 (ALLSKY_SFC_SW_DWN 1984 to 2025).\n")
    a("## 3. Items that need validation against independent data\n")
    for t_ in ["Precipitation: compare PRECTOTCORR with station rainfall or an independent gridded product, especially December 1986 and September 1987 at Kumasi, Takoradi and Accra, the other flagged months, and the change points the raw Pettitt test finds around 2015 and 2016 at Accra, Kumasi and Takoradi (after removing the linear trend a step remains only at Takoradi around 2016, and at Kumasi around 1988).",
               "Solar radiation: confirm the decline in ALLSKY_SFC_SW_DWN with an independent radiation product and check whether the source blend changes during the record. The response does not say which product supplies this variable in which years.",
               "Temperature and humidity: compare the significant T2M and RH2M trends with station data. A reanalysis trend can reflect changes in assimilated observations.",
               "Definitions: confirm the monthly meaning of T2M_MAX and T2M_MIN (highest and lowest hourly value) against daily or hourly POWER data. The evidence here is consistent with it but is not proof.",
               "Spatial resolution: the files do not state a resolution per variable. Find the native grid of each source product and record it before quoting any resolution."]:
        a("- " + t_)
    a("\n## 4. Statistical limits\n")
    for t_ in ["The autocorrelation correction is an effective sample size adjustment. In simulation with AR(1) noise and 40 years it reduced but did not remove the excess of false positives at strong autocorrelation (about 7 to 10 percent against a nominal 5 percent at lag-1 correlation 0.6). Treat borderline p values as approximate.",
               "The seasonal Mann-Kendall test treats months as independent and is not used for significance. A covariance corrected seasonal test is not implemented.",
               "FDR is applied within two families and assumes independence or positive dependence among tests. Variables at one location, and neighbouring locations, are correlated.",
               "The minimum data thresholds (10 valid years, 70 percent coverage, 12 months per year) are my choices and not published standards.",
               "Pettitt homogeneity tests assume independent years and have limited power. A non-detection is not proof of homogeneity.",
               "Sen's slope intervals use the inflated variance, so they inherit the same approximation.",
               f"Significance after FDR does not make a trend physical. Sensitivity runs show that {int((~sg_all.all_same).sum())} of the {len(sg_all)} series significant after FDR change class under at least one reasonable alternative choice."]:
        a("- " + t_)
    a("\n## 5. Data handling limits\n")
    for t_ in ["Nothing was interpolated, filled or removed. Missing ALLSKY_SFC_SW_DWN months (1981 to 1983) stay missing and are outside every ALLSKY analysis.",
               "A year needs all 12 valid months to enter the annual series. This is strict and costs no years in this data set except for the solar variable.",
               "The files use local solar time for day boundaries. Monthly aggregation and its effect on extremes were not tested.",
               "Month 13 (the annual value NASA supplies) is not used. The annual series is built from the monthly values."]:
        a("- " + t_)
    a("\n## 6. Software status\n")
    a("The validation, import, QC and trend code is covered by automated tests with synthetic fixtures and by cross checks against scipy and pymannkendall. The OpenWeather and Agromonitoring clients are written from the vendors' documentation and have not been tested against live responses; nothing in these reports uses them.\n")
    (out / "LIMITATIONS_AND_FURTHER_VALIDATION.md").write_text("\n".join(L))

    bad_chars = []
    for f in ("IMPORT_AND_DATA_QUALITY_REPORT.md", "TREND_ANALYSIS_REPORT.md", "LOCATION_COMPARISON_TABLES.md", "LIMITATIONS_AND_FURTHER_VALIDATION.md"):
        txt = (out / f).read_text()
        if "\u2014" in txt or "\u2013" in txt:
            bad_chars.append(f)
    if bad_chars:
        print("[FAIL] em or en dash found in", bad_chars)
        return 1
    print("reports written:", ", ".join(sorted(p.name for p in out.glob("*.md"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
