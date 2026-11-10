"""Regression tests for calendar integrity. Flagged or missing observations must keep their calendar
position as NaN; the date range must never shrink; the nominal span must count flagged years.
Synthetic inputs are software tests only."""
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scipy import stats

from earthscope import config
from earthscope.ingest import power
from earthscope.qc import checks
from earthscope.spatial import grid
from earthscope.trends import engine
from earthscope.trends.pipeline import annual_series, monthly_series, run_trends
from tests import synthetic


def _frame(start=1981, end=2020, flag_years=(), **kw):
    """T2M with an exact linear trend (0.03 per year, no noise). Values in flag_years are set to a
    physically impossible 99 C so QC flags them out_of_range (value is kept, flag is set)."""
    kw.setdefault("noise", 0)
    kw.setdefault("trend", 0.03)
    df = power.parse_json(synthetic.make_payload(5.6, -0.19, start, end, **kw), "Accra")
    df = df[df.variable == "T2M"].copy()
    df.loc[df.date.dt.year.isin(flag_years), "value"] = 99.0
    return checks.add_qc_flag(df.reset_index(drop=True))


def _group(df):
    return df[(df.location == "Accra") & (df.variable == "T2M")]


CASES = [pytest.param(1981, id="entirely_flagged_FIRST_year"),
         pytest.param(2020, id="entirely_flagged_LAST_year"),
         pytest.param(2000, id="entirely_flagged_MIDDLE_year")]


@pytest.mark.parametrize("bad_year", CASES)
def test_flagged_year_keeps_its_calendar_positions(bad_year):
    clean, flagged = _frame(), _frame(flag_years=[bad_year])
    m_clean, m = monthly_series(_group(clean)), monthly_series(_group(flagged))
    # complete original range, regular monthly spacing, same length as the unflagged series
    assert len(m) == 480 and m.index[0] == pd.Timestamp("1981-01-01") and m.index[-1] == pd.Timestamp("2020-12-01")
    assert (m.index == pd.date_range("1981-01-01", "2020-12-01", freq="MS")).all()
    # NaN exactly at the twelve months of the flagged year, nowhere else
    expected_nan = pd.date_range(f"{bad_year}-01-01", f"{bad_year}-12-01", freq="MS")
    assert list(m.index[m.isna()]) == list(expected_nan)
    # every other month is untouched and still at its own date
    keep = ~m.index.isin(expected_nan)
    assert np.array_equal(m[keep].values, m_clean[keep].values)
    # the annual series still has a label for the flagged year, as NaN
    ann = annual_series(m)
    assert list(ann.index) == list(range(1981, 2021)) and np.isnan(ann.loc[bad_year]) and ann.drop(bad_year).notna().all()


@pytest.mark.parametrize("bad_year", CASES)
def test_flagged_year_counts_in_the_nominal_span_and_does_not_bend_the_slope(bad_year):
    t, an = run_trends(_frame(flag_years=[bad_year]))
    r = t.iloc[0]
    assert r.n_years == 39 and r.n_years_span == 40 and r.mk_reason == ""
    assert r.first_year_nominal == 1981 and r.last_year_nominal == 2020
    assert r.first_year == (1982 if bad_year == 1981 else 1981) and r.last_year == (2019 if bad_year == 2020 else 2020)
    assert abs(r.seasonal_sen_per_decade - 0.3) < 1e-9                     # exact: calendar identity kept
    assert abs(r.sen_per_decade - 0.3) < 0.01                               # annual means differ slightly by month length
    # the anomaly table keeps all 480 calendar positions and says why the flagged ones are empty
    assert len(an) == 480
    bad = an[an.date.dt.year == bad_year]
    assert len(bad) == 12 and bad.z.isna().all() and (bad.qc_flag == "out_of_range").all()
    assert an[an.date.dt.year != bad_year].qc_flag.eq("ok").all()


def test_leading_and_trailing_flagged_blocks_count_against_coverage():
    """15 of 45 years flagged at the START: valid years cover 67% of the nominal 45 year span, below the
    70% rule. Measuring the span from the first valid year (the old behaviour) would show 100% and report a trend."""
    lead = run_trends(_frame(1981, 2025, flag_years=range(1981, 1996)))[0].iloc[0]
    assert lead.n_years == 30 and lead.n_years_span == 45
    assert lead.mk_trend == "insufficient_data" and "45 year span" in lead.mk_reason
    assert lead.seasonal_trend == "insufficient_data" and "span" in lead.seasonal_reason
    trail = run_trends(_frame(1981, 2025, flag_years=range(2011, 2026)))[0].iloc[0]
    assert trail.n_years == 30 and trail.mk_trend == "insufficient_data" and "45 year span" in trail.mk_reason
    ok = run_trends(_frame(1981, 2025, flag_years=range(1981, 1991)))[0].iloc[0]       # 10 flagged: 35/45 = 78%
    assert ok.mk_reason == "" and ok.n_years == 35 and ok.n_years_span == 45


def test_series_with_everything_flagged_keeps_its_full_range():
    df = _frame(flag_years=range(1981, 2021))
    m = monthly_series(_group(df))
    assert len(m) == 480 and m.isna().all()
    r = run_trends(df)[0].iloc[0]
    assert r.n_years == 0 and r.n_years_span == 40 and r.mk_trend == "insufficient_data"


def test_months_absent_from_the_input_are_nan_not_removed():
    df = power.parse_json(synthetic.make_payload(5.6, -0.19, 1981, 2020, noise=0, drop_years=[1981, 2020]), "Accra")
    df = checks.add_qc_flag(df[df.variable == "T2M"])
    m = monthly_series(df)
    assert len(m) == 38 * 12 and m.index[0] == pd.Timestamp("1982-01-01")      # range is that of the rows present
    df2 = power.parse_json(synthetic.make_payload(5.6, -0.19, 1981, 2020, noise=0, drop_years=[2000]), "Accra")
    m2 = monthly_series(checks.add_qc_flag(df2[df2.variable == "T2M"]))
    assert len(m2) == 480 and m2[m2.index.year == 2000].isna().all()           # a gap inside the range is filled with NaN


def test_qc_helpers_distinguish_flagged_from_absent():
    df = _frame(flag_years=[2000])
    g = checks.gaps(df)
    assert g.absent_months.iat[0] == 0                                         # flagged is not absent
    c = checks.completeness(df).iloc[0]
    assert c.n_out_of_range == 12 and c.n_months == 480 and c.n_valid == 468


def test_monthly_series_refuses_duplicate_dates():
    df = _frame()
    with pytest.raises(ValueError, match="duplicate"):
        monthly_series(pd.concat([_group(df), _group(df).head(1)]))


# ---------------------------------------------------------------- engine level
def test_engine_counts_leading_nan_years_in_the_span():
    yrs = np.arange(1981, 2026)
    s = pd.Series(0.03 * (yrs - 1981), index=yrs)
    s[yrs < 1996] = np.nan
    r = engine.mann_kendall(s)
    assert r["n"] == 30 and r["n_span"] == 45 and r["trend"] == "insufficient_data"
    assert np.isnan(engine.sens_slope_per_decade(s))
    # the same values passed WITHOUT the NaN years (caller removed them) have a 30 year span: documented behaviour
    assert engine.mann_kendall(s.dropna())["n_span"] == 30


def test_engine_seasonal_counts_leading_nan_years_in_the_span():
    idx = pd.date_range("1981-01-01", "2025-12-01", freq="MS")
    s = pd.Series(3 * np.sin(2 * np.pi * idx.month / 12) + 0.01 * np.arange(len(idx)), index=idx)
    s[s.index.year < 1996] = np.nan
    r = engine.seasonal_mann_kendall(s)
    assert r["trend"] == "insufficient_data" and "45 year span" in r["reason"]
    assert engine.seasonal_mann_kendall(s, min_coverage=0.5)["reason"] == ""


def test_anomalies_keep_every_calendar_position():
    idx = pd.date_range("1981-01-01", "2020-12-01", freq="MS")
    s = pd.Series(np.random.default_rng(1).normal(25, 1, len(idx)), index=idx)
    s[s.index.year == 1981] = np.nan
    a = engine.climatology_anomalies(s)
    assert len(a) == 480 and a[a.index.year == 1981].z.isna().all() and not a[a.index.year == 1981].flag.any()
    assert a[a.index.year > 1981].z.notna().all()


def test_grid_counts_leading_nan_years_in_the_nominal_span():
    yrs = np.arange(1981, 2026)
    v = np.tile((0.05 * (yrs - 1981))[:, None, None], (1, 2, 2)).astype(float)
    v[yrs < 1996, 0, 0] = np.nan                                              # 15 leading years missing in one cell
    ds = grid.grid_trends(xr.DataArray(v, dims=("year", "lat", "lon"),
                                       coords={"year": yrs, "lat": [0., 1.], "lon": [0., 1.]}))
    assert np.isnan(float(ds.sen_per_decade[0, 0])) and int(ds.n_valid_years[0, 0]) == 30
    assert abs(float(ds.sen_per_decade[1, 1]) - 0.5) < 1e-12


# ---------------------------------------------------------------- annual statistic per variable
def test_annual_extremes_use_the_max_and_min_of_the_months_and_need_all_twelve():
    idx = pd.date_range("2000-01-01", "2002-12-01", freq="MS")
    vals = np.arange(36, dtype=float)
    s = pd.Series(vals, index=idx)
    s["2001-05-01"] = np.nan
    mx, mn = annual_series(s, how="max"), annual_series(s, how="min")
    assert mx.loc[2000] == 11 and mn.loc[2000] == 0 and mx.loc[2002] == 35 and mn.loc[2002] == 24
    assert np.isnan(mx.loc[2001]) and np.isnan(mn.loc[2001])                    # eleven valid months is not enough
    with pytest.raises(ValueError):
        annual_series(s, how="median")


def test_extreme_variables_default_to_annual_extremes_and_match_scipy():
    assert config.annual_how("T2M_MAX") == "max" and config.annual_how("T2M_MIN") == "min"
    assert config.annual_how("T2M") == "day_weighted_mean" and config.annual_how("PRECTOTCORR") == "day_weighted_mean"
    df = _frame(noise=0.4, seed=4)
    df["variable"] = "T2M_MAX"                                                # reuse the synthetic series as an extreme parameter
    t, _ = run_trends(df)
    r = t.iloc[0]
    assert r.annual_statistic == "max"
    g = df.assign(year=df.date.dt.year).groupby("year").value.max()
    assert abs(r.sen_per_decade - stats.theilslopes(g.values, g.index.values)[0] * 10) < 1e-12
    mean_version, _ = run_trends(df, aggregation={"T2M_MAX": "day_weighted_mean"})
    assert mean_version.iloc[0].annual_statistic == "day_weighted_mean"


def bh_by_hand(p):
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    m = len(p)
    adj = np.minimum.accumulate((p[order] * m / np.arange(1, m + 1))[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    return out


def test_fdr_is_applied_within_each_family_separately():
    frames = []
    for i, (name, var) in enumerate([("A", "T2M"), ("B", "T2M"), ("C", "T2M"), ("D", "T2M"), ("E", "T2M"), ("F", "RH2M")]):
        d = power.parse_json(synthetic.make_payload(5.6, -0.19, 1981, 2020, trend=0.01 * i, noise=0.5, seed=i), name)
        frames.append(d[d.variable == "T2M"].assign(variable=var))
    df = checks.add_qc_flag(pd.concat(frames, ignore_index=True))
    t, _ = run_trends(df, fdr_families={"RH2M": "second"})
    main = t[t.fdr_family == "primary"]
    assert len(main) == 5 and (main.n_tests_in_family == 5).all()
    assert np.allclose(main.mk_p_fdr.values, bh_by_hand(main.mk_p.values))
    only = t[t.fdr_family == "second"]
    assert len(only) == 1 and only.mk_p_fdr.iat[0] == only.mk_p.iat[0] and only.n_tests_in_family.iat[0] == 1
