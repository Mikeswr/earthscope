import numpy as np
import pandas as pd
import pytest

from earthscope.forecasting.engine import ForecastError, forecast_monthly


def seasonal_trend_series(start="1981-01-01", periods=540, seed=4):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=periods, freq="MS")
    t = np.arange(periods)
    seasonal = 2.0 * np.sin(2 * np.pi * (idx.month.to_numpy() - 1) / 12)
    values = 24 + 0.0015 * t + seasonal + rng.normal(0, 0.15, periods)
    return pd.Series(values, index=idx)


def test_forecast_returns_monthly_dates_and_ordered_intervals():
    s = seasonal_trend_series()
    fc, info = forecast_monthly(s, horizon_months=24)
    assert len(fc) == 24
    assert fc.date.iloc[0] == pd.Timestamp("2026-01-01")
    assert fc.date.iloc[-1] == pd.Timestamp("2027-12-01")
    assert (fc.lower_95 <= fc.lower_80).all()
    assert (fc.lower_80 <= fc.forecast).all()
    assert (fc.forecast <= fc.upper_80).all()
    assert (fc.upper_80 <= fc.upper_95).all()
    assert info["n_training_months"] == 540
    assert info["n_origins"] >= 3
    assert info["selected_model"] in info["metrics"]


def test_forecast_does_not_interpolate_internal_missing_months():
    s = seasonal_trend_series()
    s.iloc[250] = np.nan
    with pytest.raises(ForecastError, match="missing month"):
        forecast_monthly(s)


def test_forecast_rejects_short_record_and_long_horizon():
    with pytest.raises(ForecastError, match="at least 120"):
        forecast_monthly(seasonal_trend_series(periods=100))
    with pytest.raises(ForecastError, match="between 1 and 60"):
        forecast_monthly(seasonal_trend_series(), horizon_months=61)


def test_forecast_respects_physical_bounds_when_requested():
    s = seasonal_trend_series()
    fc, _ = forecast_monthly(s, horizon_months=12, lower_bound=0, upper_bound=100)
    assert (fc[["forecast", "lower_80", "upper_80", "lower_95", "upper_95"]] >= 0).all().all()
    assert (fc[["forecast", "lower_80", "upper_80", "lower_95", "upper_95"]] <= 100).all().all()
