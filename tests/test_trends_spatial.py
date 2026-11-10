"""Trend pipeline and spatial engine tests (synthetic inputs are software tests only)."""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from earthscope.ingest import power
from earthscope.qc import checks
from earthscope.spatial import grid
from earthscope.trends.pipeline import annual_series, monthly_series, run_trends
from tests import synthetic


def _frame(name, lat, lon, **kw):
    return power.parse_json(synthetic.make_payload(lat, lon, **kw), name)


def _df(*frames):
    return checks.add_qc_flag(pd.concat(frames, ignore_index=True))


def ar1(rng, n, phi):
    e = rng.normal(size=n + 50)
    x = np.zeros(n + 50)
    for i in range(1, n + 50):
        x[i] = phi * x[i - 1] + e[i]
    return x[50:]


YEARS = np.arange(1981, 2021)


# ---------------------------------------------------------------- annual aggregation (hand calculated)
def test_annual_mean_is_weighted_by_days_in_month():
    idx = pd.date_range("1999-01-01", "2000-12-01", freq="MS")
    s = pd.Series(list(range(1, 13)) * 2, index=idx, dtype=float)
    ann = annual_series(s)
    # sum(month * days) = 2382 over 365 days (1999); 2384 over 366 days in leap year 2000
    assert abs(ann.loc[1999] - 2382 / 365) < 1e-12 and abs(ann.loc[2000] - 2384 / 366) < 1e-12


def test_year_needs_all_twelve_valid_months():
    df = _df(_frame("Accra", 5.6, -0.19, start=1981, end=2000))
    m = (df.variable == "T2M") & (df.date == "1990-07-01")
    df.loc[m, "value"] = np.nan
    df = checks.add_qc_flag(df.drop(columns="qc_flag"))
    ann = annual_series(monthly_series(df[df.variable == "T2M"]))
    assert np.isnan(ann.loc[1990]) and ann.drop(1990).notna().all()


def test_flagged_out_of_range_values_are_excluded():
    df = _df(_frame("Accra", 5.6, -0.19, start=1981, end=2000))
    m = (df.variable == "T2M") & (df.date.dt.year == 2000)
    df.loc[m, "value"] = 99.0
    df = checks.add_qc_flag(df.drop(columns="qc_flag"))
    ann = annual_series(monthly_series(df[df.variable == "T2M"]))
    assert 2000 not in ann.dropna().index and 1999 in ann.dropna().index   # flagged year contributes nothing


# ---------------------------------------------------------------- pipeline with gaps
def test_pipeline_recovers_known_trend_and_fdr():
    df = _df(_frame("Accra", 5.6, -0.19, trend=0.03, seed=1), _frame("Tamale", 9.4, -0.84, trend=0.0, seed=2))
    t, an = run_trends(df)
    acc = t[(t.location == "Accra") & (t.variable == "T2M")].iloc[0]
    tam = t[(t.location == "Tamale") & (t.variable == "T2M")].iloc[0]
    assert acc.mk_trend == "increasing" and abs(acc.sen_per_decade - 0.3) < 0.05
    assert bool(acc.significant_fdr) and not bool(tam.significant_fdr)
    assert abs(acc.seasonal_sen_per_decade - 0.3) < 0.05
    assert (t.mk_p_fdr.dropna() >= t.mk_p.dropna()).all()
    assert {"anomaly", "z", "flag"} <= set(an.columns)
    assert acc.statistic == "monthly_mean_of_daily_mean" and acc.unit == "C"
    assert acc.autocorrelation_method == "ar1_neff"


def test_pipeline_with_missing_months_in_the_file():
    """Months ABSENT from the file (not -999) in five different years. Those years leave the annual
    series; the seasonal slope must stay exact because calendar identity is kept."""
    drop = [(1985, 3), (1990, 7), (1996, 1), (2003, 11), (2012, 5)]
    df = _df(_frame("Accra", 5.6, -0.19, trend=0.03, noise=0, drop_months=drop))
    t, _ = run_trends(df)
    r = t[(t.location == "Accra") & (t.variable == "T2M")].iloc[0]
    assert r.n_years == 35 and r.n_years_span == 40
    assert abs(r.seasonal_sen_per_decade - 0.3) < 1e-9
    assert abs(r.sen_per_decade - 0.3) < 0.01          # annual means differ slightly by month length


def test_pipeline_with_missing_years_in_the_file():
    df = _df(_frame("Accra", 5.6, -0.19, trend=0.03, noise=0, drop_years=range(1995, 2006)))
    t, _ = run_trends(df)
    r = t[(t.location == "Accra") & (t.variable == "T2M")].iloc[0]
    assert r.n_years == 29 and r.n_years_span == 40 and r.mk_reason == ""
    assert abs(r.seasonal_sen_per_decade - 0.3) < 1e-9 and abs(r.sen_per_decade - 0.3) < 0.01


def test_too_little_data_gives_a_reason_not_a_number():
    df = _df(_frame("Accra", 5.6, -0.19, start=2015, end=2019))
    t, _ = run_trends(df)
    assert (t.mk_trend == "insufficient_data").all() and t.mk_p.isna().all()
    assert t.mk_reason.str.contains("valid years").all() and t.seasonal_reason.ne("").all()


def test_fdr_family_separates_uncorrected_from_corrected():
    frames = [_frame("Trend", 5.6, -0.19, trend=0.03, seed=1)]
    frames += [_frame(f"Null{i}", 5.6, -0.19, trend=0.0, seed=10 + i) for i in range(12)]
    t, _ = run_trends(_df(*frames))
    sub = t[t.variable == "T2M"]
    assert (sub.significant_fdr <= sub.significant_uncorrected).all()
    assert bool(sub[sub.location == "Trend"].significant_fdr.iat[0])
    assert (sub.mk_p_fdr >= sub.mk_p).all()


# ---------------------------------------------------------------- spatial engine
def _cube(values, lat=None, lon=None):
    ny, nlat, nlon = values.shape
    return xr.DataArray(values, dims=("year", "lat", "lon"),
                        coords={"year": YEARS[:ny], "lat": lat if lat is not None else np.arange(float(nlat)),
                                "lon": lon if lon is not None else np.arange(float(nlon))})


@pytest.mark.parametrize("gap", [(1990, 2000), (1993, 2006), (1986, 2008)])
def test_grid_missing_years_keep_real_elapsed_time(gap):
    v = (0.05 * (YEARS - 1981)).astype(float)
    v[(YEARS >= gap[0]) & (YEARS <= gap[1])] = np.nan
    out = grid.grid_trends(_cube(v[:, None, None]), min_coverage=0.0)
    assert abs(float(out.sen_per_decade[0, 0]) - 0.5) < 1e-12     # exact; compressing years would not be


def test_grid_default_thresholds_reject_sparse_cells():
    v = (0.05 * (YEARS - 1981)).astype(float)
    v[5:28] = np.nan                                               # 23 of 40 years missing
    out = grid.grid_trends(_cube(v[:, None, None]))
    assert np.isnan(float(out.sen_per_decade[0, 0])) and int(out.n_valid_years[0, 0]) == 17


def test_grid_year_coordinate_is_required_and_validated():
    vals = np.zeros((40, 2, 2))
    no_coord = xr.DataArray(vals, dims=("year", "lat", "lon"), coords={"lat": [0., 1.], "lon": [0., 1.]})
    with pytest.raises(ValueError, match="year"):
        grid.grid_trends(no_coord)
    for bad in (YEARS[::-1], np.r_[YEARS[:-1], YEARS[0]], YEARS + 0.5):
        with pytest.raises(ValueError):
            grid.grid_trends(xr.DataArray(vals, dims=("year", "lat", "lon"),
                                          coords={"year": bad, "lat": [0., 1.], "lon": [0., 1.]}))


def test_grid_spatially_varying_trends_with_fdr():
    rng = np.random.default_rng(0)
    nlon = 8
    true = np.zeros((8, nlon))
    true[:, 4:] = 0.02 * (np.arange(4, nlon) - 3)                  # 0.02 .. 0.08 per year on the east half
    vals = np.stack([[0.0 + true[i, j] * (YEARS - 1981) + rng.normal(0, 0.3, 40) for j in range(nlon)]
                     for i in range(8)]).transpose(2, 0, 1)
    ds = grid.grid_trends(_cube(vals))
    est, truth = ds.sen_per_decade.values, true * 10
    assert np.corrcoef(est.ravel(), truth.ravel())[0, 1] > 0.95
    assert np.abs(est - truth).mean() < 0.1
    sig = ds.significant_fdr.values
    assert sig[:, 5:].all()                                         # clearly trending cells are found
    assert sig[:, :4].sum() <= 2                                    # null half: at most a stray false positive
    assert (ds.significant_fdr <= ds.significant_uncorrected).all() # corrected never exceeds uncorrected
    assert (ds.p_fdr.values[np.isfinite(ds.p_fdr.values)] >= ds.p_uncorrected.values[np.isfinite(ds.p_uncorrected.values)]).all()


def test_grid_autocorrelation_option_changes_false_positives():
    rng = np.random.default_rng(7)
    v = np.stack([[ar1(rng, 40, 0.6) for _ in range(12)] for _ in range(12)]).transpose(2, 0, 1)   # null field
    none = grid.grid_trends(_cube(v), autocorrelation="none")
    neff = grid.grid_trends(_cube(v), autocorrelation="ar1_neff")
    sn, sa = grid.field_summary(none), grid.field_summary(neff)
    assert sa["significant_uncorrected"] < sn["significant_uncorrected"]
    assert sa["significant_fdr"] <= sn["significant_fdr"]
    assert sa["cells_tested"] == 144 and sa["expected_false_positives_uncorrected_if_no_trend"] == 7.2
    assert (neff.variance_factor.values >= 1.0).all()


def test_field_summary_reports_both_kinds_of_significance():
    rng = np.random.default_rng(1)
    v = rng.normal(size=(40, 6, 6))
    ds = grid.grid_trends(_cube(v))
    s = grid.field_summary(ds)
    assert {"significant_uncorrected", "significant_fdr", "fdr_method", "autocorrelation"} <= set(s)
    assert ds.attrs["fdr_method"] == "bh" and ds.attrs["n_tests"] == 36


def test_benjamini_yekutieli_is_more_conservative_than_bh():
    rng = np.random.default_rng(2)
    v = rng.normal(size=(40, 10, 10)) + 0.03 * (YEARS - 1981)[:, None, None] * (rng.random((1, 10, 10)) > 0.5)
    bh = grid.field_summary(grid.grid_trends(_cube(v), fdr_method="bh"))["significant_fdr"]
    by = grid.field_summary(grid.grid_trends(_cube(v), fdr_method="by"))["significant_fdr"]
    assert by <= bh


def test_point_map_builds_three_groups():
    t, _ = run_trends(_df(_frame("Accra", 5.6, -0.19, trend=0.03, seed=1), _frame("Tamale", 9.4, -0.84, trend=0.0, seed=2)))
    fig = grid.point_trend_map(t, "T2M")
    assert len(fig.data) >= 1


# ---------------------------------------------------------------- FDR must really be applied
def bh_by_hand(p):
    """Benjamini-Hochberg written out independently of engine.fdr_adjust and statsmodels."""
    p = np.asarray(p, dtype=float)
    ok = np.where(~np.isnan(p))[0]
    order = ok[np.argsort(p[ok])]
    m = len(order)
    adj = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.full_like(p, np.nan)
    out[order] = np.minimum(adj, 1.0)
    return out


def test_grid_fdr_equals_hand_written_benjamini_hochberg_and_changes_outcomes():
    rng = np.random.default_rng(5)
    v = rng.normal(size=(40, 12, 12))                                  # null field, independent years
    v[:, :3, :3] += 0.12 * (YEARS - 1981)[:, None, None]               # nine strongly trending cells (z about 9)
    ds = grid.grid_trends(_cube(v), autocorrelation="none")
    p = ds.p_uncorrected.values.ravel()
    assert np.allclose(ds.p_fdr.values.ravel(), bh_by_hand(p), equal_nan=True)
    assert (ds.p_fdr.values > ds.p_uncorrected.values + 1e-12).sum() > 100       # correction actually moved p values
    s = grid.field_summary(ds)
    assert s["significant_fdr"] < s["significant_uncorrected"]                   # some uncorrected hits do not survive
    assert ds.significant_fdr.values[:3, :3].all()                               # real trends do survive


def test_trend_table_fdr_equals_hand_written_benjamini_hochberg():
    frames = [_frame("Trend", 5.6, -0.19, trend=0.03, seed=1)]
    frames += [_frame(f"Null{i}", 5.6, -0.19, trend=0.0, seed=20 + i, noise=0.5) for i in range(15)]
    t, _ = run_trends(_df(*frames))
    assert np.allclose(t.mk_p_fdr.values, bh_by_hand(t.mk_p.values), equal_nan=True)
    assert (t.mk_p_fdr > t.mk_p + 1e-12).sum() >= 10
    assert t.n_tests_in_family.iat[0] == t.mk_p.notna().sum()
