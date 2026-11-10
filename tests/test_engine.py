"""Statistics tests. References are INDEPENDENT of the engine: hand calculations, scipy, and
pymannkendall on complete data. Synthetic series are software test inputs only."""
import numpy as np
import pandas as pd
import pymannkendall as pmk
import pytest
from scipy import stats

from earthscope.trends import engine


def ar1(rng, n, phi):
    e = rng.normal(size=n + 50)
    x = np.zeros(n + 50)
    for i in range(1, n + 50):
        x[i] = phi * x[i - 1] + e[i]
    return x[50:]


YEARS = np.arange(1981, 2021)


# ---------------------------------------------------------------- hand calculated references
def test_mk_hand_example_monotone_five_points():
    # S = 10, Var = 5*4*15/18 = 16.667, z = (10-1)/sqrt(16.667) = 2.20454, p = 0.02749 (hand/normal table)
    r = engine.mann_kendall(pd.Series([1, 2, 3, 4, 5], index=range(2000, 2005)), min_valid=5, min_coverage=0,
                            autocorrelation="none")
    assert r["S"] == 10 and abs(r["var_s"] - 16.6667) < 1e-3
    assert abs(r["z"] - 2.20454) < 1e-4 and abs(r["p"] - 0.02749) < 1e-4 and r["trend"] == "increasing"


def test_sen_hand_example_unequal_spacing():
    # t = 0,1,3 ; x = 0,1,6 -> pair slopes 1/1, 6/3, 5/2 = 1, 2, 2.5 -> median 2.0
    assert engine.sens_slope([0, 1, 6], [0, 1, 3]) == 2.0
    # treating the same three values as consecutive years (t = 0,1,2): 1/1, 6/2, 5/1 = 1, 3, 5 -> median 3.0
    assert engine.sens_slope([0, 1, 6], [0, 1, 2]) == 3.0


def test_seasonal_hand_example_complete_and_with_a_missing_year():
    # every calendar month holds values (0, 1, 3) in years 2000, 2001, 2002
    idx = pd.to_datetime([f"{y}-{m:02d}-01" for y in (2000, 2001, 2002) for m in range(1, 13)])
    vals = [v for v in (0, 1, 3) for _ in range(12)]
    s = pd.Series(vals, index=idx, dtype=float)
    r = engine.seasonal_mann_kendall(s, min_years_per_month=3, min_coverage=0)
    # per month S = 3, var = 3*2*11/18 = 3.6667 -> S = 36, var = 44, z = 35/sqrt(44) = 5.27645
    assert r["S"] == 36 and abs(r["var_s"] - 44) < 1e-9 and abs(r["z"] - 5.27645) < 1e-4
    assert r["slope"] == 1.5  # per-month slopes 1/1, 3/2, 2/1 -> median 1.5
    # remove 2001 for May only: that month has (0 in 2000, 3 in 2002): S = 1, var = 1, slope = 1.5
    s2 = s.drop(pd.Timestamp("2001-05-01"))
    r2 = engine.seasonal_mann_kendall(s2, min_years_per_month=2, min_coverage=0)
    assert r2["S"] == 34 and abs(r2["var_s"] - (11 * 3.66667 + 1)) < 1e-3
    assert r2["slope"] == 1.5


# ---------------------------------------------------------------- independent implementations
def test_matches_scipy_and_pymannkendall_on_complete_data():
    rng = np.random.default_rng(5)
    x = 0.02 * (YEARS - 1981) + rng.normal(0, 0.4, 40)
    a = pd.Series(x, index=YEARS)
    mine = engine.mann_kendall(a, autocorrelation="none")
    ref = pmk.original_test(x)
    assert abs(mine["z"] - ref.z) < 1e-9 and abs(mine["p"] - ref.p) < 1e-9
    assert abs(mine["slope"] - ref.slope) < 1e-12
    assert abs(mine["slope"] - stats.theilslopes(x, YEARS)[0]) < 1e-12
    # S from scipy's Kendall tau (no ties): S = tau * n(n-1)/2
    assert abs(mine["S"] - stats.kendalltau(YEARS, x)[0] * 40 * 39 / 2) < 1e-9


def test_hamed_rao_option_reproduces_pymannkendall():
    rng = np.random.default_rng(6)
    x = np.convolve(rng.normal(0, 1, 60), [0.6, 0.4], "same")[:40] + 0.02 * (YEARS - 1981)
    mine = engine.mann_kendall(pd.Series(x, index=YEARS), autocorrelation="hamed_rao")
    ref = pmk.hamed_rao_modification_test(x)
    assert abs(mine["z"] - ref.z) < 1e-9 and abs(mine["p"] - ref.p) < 1e-9


def test_seasonal_complete_data_matches_pymannkendall():
    idx = pd.date_range("1981-01-01", periods=480, freq="MS")
    rng = np.random.default_rng(1)
    y = 3 * np.sin(2 * np.pi * idx.month / 12) + 0.01 * np.arange(480) + rng.normal(0, 0.3, 480)
    mine = engine.seasonal_mann_kendall(pd.Series(y, index=idx))
    ref = pmk.seasonal_test(y, period=12)
    assert abs(mine["z"] - ref.z) < 1e-9 and abs(mine["slope"] - ref.slope) < 1e-12


def test_sen_matches_scipy_with_real_year_gaps():
    rng = np.random.default_rng(2)
    keep = np.sort(rng.choice(YEARS, 28, replace=False))
    x = 0.03 * (keep - 1981) + rng.normal(0, 0.2, 28)
    assert abs(engine.sens_slope(x, keep) - stats.theilslopes(x, keep)[0]) < 1e-12


# ---------------------------------------------------------------- missing data: temporal integrity
def _monthly_exact(slope_per_month=0.01):
    idx = pd.date_range("1981-01-01", periods=480, freq="MS")
    return pd.Series(3 * np.sin(2 * np.pi * idx.month / 12) + slope_per_month * np.arange(480), index=idx)


def test_missing_months_do_not_shift_calendar_identity():
    s = _monthly_exact()                                  # exact slope 0.12 per year
    rng = np.random.default_rng(0)
    s[rng.random(480) < 0.2] = np.nan                     # 20% random loss, coverage still above 70%
    r = engine.seasonal_mann_kendall(s)
    assert r["reason"] == "" and abs(r["slope"] - 0.12) < 1e-12
    # structured loss: all Januaries of the first 8 years and all Julys of the last 8 years
    s2 = _monthly_exact()
    s2[(s2.index.month == 1) & (s2.index.year < 1989)] = np.nan
    s2[(s2.index.month == 7) & (s2.index.year > 2012)] = np.nan
    assert abs(engine.seasonal_mann_kendall(s2)["slope"] - 0.12) < 1e-12


def test_old_compress_and_reshape_method_would_have_failed_this_test():
    """Guards the guard: dropping NaN then reshaping into rows of 12 (the earlier implementation)
    gives a different answer on the same data, so the test above really detects the bug."""
    s = _monthly_exact()
    s[np.random.default_rng(0).random(480) < 0.2] = np.nan
    wrong = pmk.seasonal_test(s.dropna().values, period=12).slope
    assert abs(wrong - 0.12) > 0.005


def test_missing_whole_years_keep_true_elapsed_time():
    ann = pd.Series(0.03 * (YEARS - 1981), index=YEARS)
    ann[(YEARS >= 1995) & (YEARS <= 2005)] = np.nan       # 11 missing years
    assert abs(engine.sens_slope_per_decade(ann) - 0.30) < 1e-12
    r = engine.mann_kendall(ann)
    assert r["n"] == 29 and r["n_span"] == 40 and abs(r["slope"] - 0.03) < 1e-12
    # treating the survivors as consecutive years (old behaviour) overstates the slope
    assert abs(pmk.sens_slope(ann.dropna().values).slope * 10 - 0.30) > 0.05


def test_seasonal_missing_whole_years_exact():
    s = _monthly_exact()
    s[(s.index.year >= 1995) & (s.index.year <= 2005)] = np.nan
    r = engine.seasonal_mann_kendall(s)
    assert r["reason"] == "" and abs(r["slope"] - 0.12) < 1e-12


# ---------------------------------------------------------------- minimum data thresholds
def test_threshold_too_few_years():
    r = engine.mann_kendall(pd.Series(np.arange(9.0), index=range(2000, 2009)))
    assert r["trend"] == "insufficient_data" and "9 valid years" in r["reason"] and np.isnan(r["p"])


def test_threshold_low_coverage_even_with_enough_years():
    yrs = list(range(1981, 1986)) + list(range(2010, 2020))        # 15 years across a 39 year span
    r = engine.mann_kendall(pd.Series(np.arange(15.0), index=yrs))
    assert r["trend"] == "insufficient_data" and "span" in r["reason"]
    assert np.isnan(engine.sens_slope_per_decade(pd.Series(np.arange(15.0), index=yrs)))


def test_threshold_seasonal_month_with_too_few_years():
    s = _monthly_exact()
    s[(s.index.month == 3) & (s.index.year > 1988)] = np.nan       # March keeps only 8 years
    r = engine.seasonal_mann_kendall(s)
    assert r["trend"] == "insufficient_data" and "month 03" in r["reason"]


def test_anomaly_needs_enough_base_years():
    idx = pd.date_range("1981-01-01", periods=480, freq="MS")
    s = pd.Series(np.random.default_rng(3).normal(25, 1, 480), index=idx)
    ok = engine.climatology_anomalies(s)
    assert ok["z"].notna().all()
    s2 = s.copy()
    s2[(s2.index.month == 4) & (s2.index.year < 2006)] = np.nan   # April base period keeps 15 years
    a = engine.climatology_anomalies(s2)
    assert a[a.index.month == 4]["z"].isna().all() and a[a.index.month != 4]["z"].notna().all()


def test_anomaly_flag_detects_extreme():
    idx = pd.date_range("1981-01-01", periods=480, freq="MS")
    s = pd.Series(np.random.default_rng(1).normal(25, 0.5, 480), index=idx)
    s.iloc[-1] = 35
    assert bool(engine.climatology_anomalies(s)["flag"].iloc[-1])


def test_index_type_errors_are_loud():
    with pytest.raises(TypeError):
        engine.mann_kendall(pd.Series(np.arange(20.0), index=pd.date_range("2000", periods=20, freq="YS")))
    with pytest.raises(TypeError):
        engine.seasonal_mann_kendall(pd.Series(np.arange(500.0)))
    with pytest.raises(ValueError):
        engine.mann_kendall(pd.Series(np.arange(12.0), index=[2000.5 + i for i in range(12)]))


# ---------------------------------------------------------------- trend detection and autocorrelation
def test_known_trend_and_no_trend():
    rng = np.random.default_rng(0)
    up = engine.mann_kendall(pd.Series(0.03 * np.arange(40) + rng.normal(0, 0.1, 40), index=YEARS))
    assert up["trend"] == "increasing" and up["p"] < 0.01 and abs(up["slope"] - 0.03) < 0.005
    flat = engine.mann_kendall(pd.Series(rng.normal(0, 1, 40), index=YEARS))
    assert flat["trend"] == "no trend"


def test_autocorrelation_correction_reduces_false_positives():
    """Monte Carlo (seeded): AR(1) noise with phi = 0.6, n = 40, no trend. Nominal error rate is 5%."""
    rng = np.random.default_rng(42)
    n_sim, hit = 400, {"none": 0, "ar1_neff": 0, "hamed_rao": 0}
    for _ in range(n_sim):
        s = pd.Series(ar1(rng, 40, 0.6), index=YEARS)
        for k in hit:
            hit[k] += engine.mann_kendall(s, autocorrelation=k)["p"] < 0.05
    rate = {k: v / n_sim for k, v in hit.items()}
    assert rate["none"] > 0.20                       # the problem is real
    assert rate["ar1_neff"] < 0.13                   # much closer to nominal (not exactly 0.05)
    assert rate["ar1_neff"] < rate["hamed_rao"] < rate["none"]   # recorded ordering in docs/METHODS.md


def test_ar1_correction_is_harmless_on_white_noise():
    rng = np.random.default_rng(8)
    n_sim, hit = 400, 0
    for _ in range(n_sim):
        hit += engine.mann_kendall(pd.Series(rng.normal(size=40), index=YEARS))["p"] < 0.05
    assert hit / n_sim < 0.08


def test_variance_factor_never_below_one_for_ar1_neff():
    rng = np.random.default_rng(9)
    for _ in range(50):
        r = engine.mann_kendall(pd.Series(rng.normal(size=40), index=YEARS))
        assert r["variance_factor"] >= 1.0


# ---------------------------------------------------------------- FDR
def test_fdr_known_values_hand_calculated():
    # p = 0.01, 0.02, 0.03, 0.5 ; BH: p*(m/rank) -> .04, .04, .04, .5 (then monotone) = 0.04, 0.04, 0.04, 0.5
    # BY multiplies by c(m) = 1 + 1/2 + 1/3 + 1/4 = 2.0833 and caps at 1: 0.0833, 0.0833, 0.0833, 1.0
    adj = engine.fdr_adjust([0.01, 0.02, 0.03, 0.5])
    assert np.allclose(adj, [0.04, 0.04, 0.04, 0.5])
    by = engine.fdr_adjust([0.01, 0.02, 0.03, 0.5], method="by")
    assert np.allclose(by, np.minimum(1.0, adj * (1 + 1 / 2 + 1 / 3 + 1 / 4)))


def test_fdr_nan_handling_and_null_control():
    adj = engine.fdr_adjust([0.001, 0.02, 0.5, np.nan])
    assert np.isnan(adj[3]) and adj[0] <= adj[1] <= adj[2]
    p = np.random.default_rng(3).uniform(size=500)
    assert (engine.fdr_adjust(p) < 0.05).sum() <= 5


# ---------------------------------------------------------------- Sen slope confidence interval, lag-1, evidence class
def test_sen_ci_contains_the_estimate_and_widens_with_variance():
    rng = np.random.default_rng(3)
    x = 0.03 * (YEARS - 1981) + rng.normal(0, 0.3, 40)
    r = engine.mann_kendall(pd.Series(x, index=YEARS), autocorrelation="none")
    assert r["slope_ci_low"] < r["slope"] < r["slope_ci_high"]
    lo2, hi2 = engine.sens_slope_ci(x, YEARS.astype(float), r["var_s"] * 4)
    assert hi2 - lo2 > r["slope_ci_high"] - r["slope_ci_low"]
    ref = stats.theilslopes(x, YEARS, alpha=0.95)           # independent implementation
    assert abs(r["slope_ci_low"] - ref[2]) < 0.002 and abs(r["slope_ci_high"] - ref[3]) < 0.002


def test_sen_ci_coverage_is_close_to_95_percent_for_independent_noise():
    rng = np.random.default_rng(10)
    hit, n_sim = 0, 400
    for _ in range(n_sim):
        x = 0.02 * (YEARS - 1981) + rng.normal(0, 0.5, 40)
        r = engine.mann_kendall(pd.Series(x, index=YEARS), autocorrelation="none")
        hit += r["slope_ci_low"] <= 0.02 <= r["slope_ci_high"]
    assert 0.92 < hit / n_sim < 0.985


def test_lag1_autocorrelation_is_reported_and_recovers_known_value():
    rng = np.random.default_rng(12)
    rho = [engine.mann_kendall(pd.Series(ar1(rng, 45, 0.6), index=np.arange(1981, 2026)))["rho1"] for _ in range(300)]
    assert 0.35 < np.mean(rho) < 0.62          # biased low for short series, as expected for n = 45
    assert np.isnan(engine.mann_kendall(pd.Series(np.arange(9.0), index=range(2000, 2009)))["rho1"])


def test_non_positive_corrected_variance_is_reported_not_hidden():
    """The Hamed-Rao factor can be <= 0 for strongly negatively autocorrelated series. That must come back as an
    explicit insufficient result, never as z = 0 / p = 1 or a crash. ar1_neff is floored at 1 and cannot do this."""
    yrs = np.arange(1981, 2021)
    x = np.where(np.arange(40) % 2 == 0, 1.0, -1.0) + 0.001 * np.arange(40)        # strict alternation
    r = engine.mann_kendall(pd.Series(x, index=yrs), autocorrelation="hamed_rao")
    if r["reason"]:                                                                 # the factor is non-positive for this series
        assert r["trend"] == "insufficient_data" and "not positive" in r["reason"] and np.isnan(r["p"])
    else:
        assert r["var_s"] > 0
    assert engine.mann_kendall(pd.Series(x, index=yrs))["reason"] == ""
    assert engine.sens_slope_ci([1, 2, 3, 4], [0, 1, 2, 3], -5.0) == (float("nan"), float("nan")) or all(
        np.isnan(v) for v in engine.sens_slope_ci([1, 2, 3, 4], [0, 1, 2, 3], -5.0))


def test_hamed_rao_non_positive_variance_count_in_the_simulation():
    rng = np.random.default_rng(42)
    bad = 0
    for _ in range(400):
        r = engine.mann_kendall(pd.Series(ar1(rng, 40, 0.6), index=np.arange(1981, 2021)), autocorrelation="hamed_rao")
        bad += bool(r["reason"])
    assert bad <= 400 * 0.05          # rare; documented in METHODS.md with the observed count
