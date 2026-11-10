"""End to end validation: raw file -> import -> processed -> trends, one scenario per concern.
All inputs are synthetic and exist only to exercise the software."""
import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from earthscope import config
from earthscope.ingest import pipeline, power
from earthscope.trends.pipeline import run_trends
from tests import synthetic


@pytest.fixture
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("EARTHSCOPE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def _load(name="Accra", lat=5.6, lon=-0.19, start=1981, end=2020, **kw):
    f = config.raw_dir() / f"power_monthly_{name}_{start}_{end}.json"
    f.write_text(json.dumps(synthetic.make_payload(lat, lon, start, end, **kw)))
    return pipeline.build_processed()


def test_missing_months_flow_through_to_qc_and_trends(datadir):
    df = _load(missing=[("T2M", "199003"), ("T2M", "199004")], drop_months=[(2001, 6)], trend=0.03, noise=0)
    t2m = df[df.variable == "T2M"]
    assert (t2m.qc_flag == "missing").sum() == 2
    assert len(t2m) == 480 - 1                                       # the absent month is simply not there
    t, _ = run_trends(df)
    r = t[t.variable == "T2M"].iloc[0]
    # 1990-03 and 1990-04 are in the same year, so two years (1990, 2001) leave the annual series
    assert r.n_years == 38 and abs(r.seasonal_sen_per_decade - 0.3) < 1e-9


def test_missing_years_flow_through_to_metadata_and_trends(datadir):
    df = _load(drop_years=range(1995, 2006), trend=0.03, noise=0)
    c = json.loads((config.processed_dir() / pipeline.METADATA_NAME).read_text())["files"][0]["actual_coverage"]["T2M"]
    assert c["months_absent_inside_span"] == 11 * 12
    r = run_trends(df)[0].query("variable == 'T2M'").iloc[0]
    assert r.n_years == 29 and abs(r.seasonal_sen_per_decade - 0.3) < 1e-9


def test_out_of_range_values_are_kept_but_never_used(datadir):
    bad = [("T2M", f"{y}0{m}", 80.0) for y in range(2000, 2010) for m in range(1, 10)]
    df = _load(bad=bad, trend=0.0, noise=0)
    flagged = df[(df.variable == "T2M") & (df.qc_flag == "out_of_range")]
    assert len(flagged) == 90 and (flagged.value == 80.0).all()      # value preserved for inspection
    r = run_trends(df)[0].query("variable == 'T2M'").iloc[0]
    assert r.n_years == 30                                           # the 10 affected years left the annual series


def test_duplicates_and_conflicts(datadir):
    (config.raw_dir() / "power_monthly_Accra_1981_1990.csv").write_text(
        synthetic.make_csv(5.6, -0.19, 1981, 1990, dup_rows=[("T2M", 1985, 0.0)]))
    pipeline.build_processed()
    (config.raw_dir() / "power_monthly_Accra_1981_1990.csv").write_text(
        synthetic.make_csv(5.6, -0.19, 1981, 1990, dup_rows=[("T2M", 1985, 1.0)]))
    with pytest.raises(ValueError, match="conflicting"):
        pipeline.build_processed()


def test_unit_problems_stop_the_pipeline(datadir):
    f = config.raw_dir() / "power_monthly_Accra_1981_1990.json"
    f.write_text(json.dumps(synthetic.make_payload(5.6, -0.19, 1981, 1990, units=None)))
    with pytest.raises(power.UnitError):
        pipeline.build_processed()
    assert not (config.processed_dir() / pipeline.PROCESSED_NAME).exists()    # nothing half written


def test_synthetic_data_is_identifiable_at_every_stage(datadir):
    df = _load()
    assert (df.source == "SYNTHETIC TEST DATA").all()
    t, _ = run_trends(df)
    assert (t.source == "SYNTHETIC TEST DATA").all() and (t.data_kind == "synthetic_test").all()


def test_pipeline_trend_matches_an_independent_calculation(datadir):
    """Annual means computed here with plain loops, then scipy Theil-Sen and Kendall tau.
    Compared with the pipeline's output for the same synthetic file."""
    df = _load(trend=0.025, noise=0.4, seed=3)
    t, _ = run_trends(df, autocorrelation="none")
    r = t[t.variable == "T2M"].iloc[0]
    g = df[df.variable == "T2M"]
    years, annual = [], []
    for y in sorted(g.date.dt.year.unique()):
        gy = g[g.date.dt.year == y]
        days = [pd.Timestamp(d).days_in_month for d in gy.date]
        years.append(y)
        annual.append(sum(v * d for v, d in zip(gy.value, days)) / sum(days))
    assert abs(r.sen_per_decade - stats.theilslopes(annual, years)[0] * 10) < 1e-12
    assert abs(r.kendall_tau - stats.kendalltau(years, annual)[0]) < 1e-12
    s_ref = stats.kendalltau(years, annual)[0] * 40 * 39 / 2
    var = 40 * 39 * (2 * 40 + 5) / 18                                  # no ties, n = 40
    z_ref = (s_ref - 1) / np.sqrt(var) if s_ref > 0 else (s_ref + 1) / np.sqrt(var)
    assert abs(r.mk_z - z_ref) < 1e-9
