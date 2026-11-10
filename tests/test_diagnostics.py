import numpy as np
import pandas as pd

from earthscope.qc import diagnostics as dg
from earthscope.trends.pipeline import run_trends
from earthscope.qc import checks
from earthscope.ingest import power
from tests import synthetic


def test_pettitt_hand_example():
    # 1,1,1,1,1 then 5,5,5,5,5: U_5 = 25 (every earlier value is smaller than every later one), K = 25
    s = pd.Series([1.0] * 5 + [5.0] * 5, index=range(2000, 2010))
    r = dg.pettitt(s)
    assert r["K"] == 25 and r["change_year"] == 2004 and r["step"] == 4.0
    assert abs(r["p"] - 2 * np.exp(-6 * 625 / (1000 + 100))) < 1e-12        # = 0.0661
    assert r["detected"] is False                                           # n = 10 is too short to detect even a perfect step at 5%


def test_pettitt_finds_a_step_and_not_noise_and_ignores_missing_years():
    rng = np.random.default_rng(1)
    yrs = np.arange(1981, 2026)
    step = pd.Series(rng.normal(0, 0.3, 45) + np.where(yrs > 2005, 1.0, 0.0), index=yrs)
    r = dg.pettitt(step)
    assert r["detected"] and abs(r["change_year"] - 2005) <= 2 and abs(r["step"] - 1.0) < 0.3
    assert not dg.pettitt(pd.Series(rng.normal(0, 1, 45), index=yrs))["detected"]
    gap = step.copy(); gap[(yrs > 1995) & (yrs < 2000)] = np.nan
    assert dg.pettitt(gap)["change_year"] in range(2003, 2008)               # labels are real years, not positions
    assert not dg.pettitt(pd.Series(np.arange(8.0), index=range(8)))["detected"]


def test_identical_runs():
    assert dg.runs_of_identical_values([1, 2, 2, 2, 2, 3, 3, np.nan, np.nan, np.nan, np.nan]) == [(1, 4)]
    assert dg.runs_of_identical_values([1, 2, 3]) == []


def test_suspicious_months_flags_an_injected_spike_and_keeps_all_positions():
    idx = pd.date_range("1981-01-01", "2020-12-01", freq="MS")
    s = pd.Series(np.random.default_rng(2).normal(25, 0.5, len(idx)), index=idx)
    s.loc["2005-03-01"] = 40.0
    s.loc["2010-01-01":"2010-12-01"] = np.nan
    summary, big = dg.suspicious_months(s)
    assert summary["n_extreme_abs_z_ge_4"] >= 1 and pd.Timestamp("2005-03-01") in big.index
    assert big.loc["2005-03-01", "level"] == "extreme" and summary["n_months_with_z"] == 480 - 12


def test_evidence_class_keeps_descriptive_slope_separate_from_significance():
    frames = [power.parse_json(synthetic.make_payload(5.6, -0.19, 1981, 2020, trend=tr, noise=0.4, seed=i), n)
              for i, (n, tr) in enumerate([("Up", 0.04), ("Flat", 0.0)])]
    frames.append(power.parse_json(synthetic.make_payload(5.6, -0.19, 2015, 2019), "Short"))
    df = checks.add_qc_flag(pd.concat(frames, ignore_index=True))
    t, _ = run_trends(df)
    t = t[t.variable == "T2M"].set_index("location")
    assert t.loc["Up", "evidence_class"] == "significant_after_fdr"
    assert t.loc["Flat", "evidence_class"] in ("not_significant", "significant_before_fdr_only")
    assert t.loc["Short", "evidence_class"] == "insufficient_data" and np.isnan(t.loc["Short", "sen_per_decade"])
    assert np.isfinite(t.loc["Flat", "sen_per_decade"])                       # descriptive slope still reported
    assert t.loc["Up", "sen_ci_low_per_decade"] < t.loc["Up", "sen_per_decade"] < t.loc["Up", "sen_ci_high_per_decade"]
    assert np.isfinite(t.loc["Up", "lag1_autocorrelation"])


def test_detrended_pettitt_ignores_a_pure_trend_but_still_finds_a_step():
    rng = np.random.default_rng(5)
    yrs = np.arange(1981, 2026)
    trend = pd.Series(0.05 * (yrs - 1981) + rng.normal(0, 0.15, 45), index=yrs)
    assert dg.pettitt(trend)["detected"] and not dg.pettitt_detrended(trend)["detected"]
    step = pd.Series(rng.normal(0, 0.3, 45) + np.where(yrs > 2005, 1.5, 0.0), index=yrs)
    assert dg.pettitt(step)["detected"] and dg.pettitt_detrended(step)["detected"]


def test_extreme_precip_exclusion_is_sensitivity_only_and_marks_the_right_months():
    import importlib, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    ra = importlib.import_module("scripts.run_analysis")
    df = power.parse_json(synthetic.make_payload(5.6, -0.19, 1981, 2020, noise=0.3), "Accra")
    df = df[df.variable == "PRECTOTCORR"].copy()
    df.loc[df.date == "1986-12-01", "value"] = 40.0
    df = checks.add_qc_flag(df.reset_index(drop=True))
    out = ra.exclude_extreme_precip(df)
    assert out.loc[out.date == "1986-12-01", "qc_flag"].iat[0] == "sensitivity_excluded"
    assert (out.qc_flag == "sensitivity_excluded").sum() == 1
    assert df.loc[df.date == "1986-12-01", "qc_flag"].iat[0] == "ok"                 # the input is not modified
    assert out.value.equals(df.value)                                                 # values untouched, only the flag differs
