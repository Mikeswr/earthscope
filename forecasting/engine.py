"""Monthly forecasting with rolling-origin model selection and empirical error bands.

This is a statistical outlook, not a climate-model projection. It extrapolates patterns in
NASA POWER point time series and must be interpreted with the backtest diagnostics returned
alongside every forecast.

No missing values are interpolated. The input must be a regular monthly DatetimeIndex with
a contiguous, complete observed segment after leading missing values are removed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

MIN_TRAIN_MONTHS = 120
MAX_HORIZON_MONTHS = 60
DEFAULT_BACKTEST_ORIGINS = 5
SEASONAL_PERIOD = 12


class ForecastError(ValueError):
    """Raised when a series is not suitable for defensible forecasting."""


def _regular_monthly_series(series: pd.Series) -> pd.Series:
    s = pd.Series(series, dtype=float).copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        raise ForecastError("The series must have a monthly DatetimeIndex.")
    if s.index.has_duplicates:
        raise ForecastError("Duplicate monthly timestamps are not allowed.")
    if len(s) == 0:
        raise ForecastError("The series is empty.")
    s.index = s.index.to_period("M").to_timestamp()
    s = s.sort_index()
    full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    s = s.reindex(full)
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None:
        raise ForecastError("The series contains no valid observations.")
    s = s.loc[first:last]
    if s.isna().any():
        missing = int(s.isna().sum())
        raise ForecastError(
            f"The observed record contains {missing} missing month(s). "
            "Forecasting will not silently interpolate gaps."
        )
    if len(s) < MIN_TRAIN_MONTHS:
        raise ForecastError(
            f"Only {len(s)} consecutive valid months are available; "
            f"at least {MIN_TRAIN_MONTHS} are required."
        )
    return s.astype(float)


def _seasonal_naive(train: np.ndarray, steps: int) -> np.ndarray:
    if len(train) < SEASONAL_PERIOD:
        raise ForecastError("Seasonal-naive forecasting needs at least 12 months.")
    return np.resize(train[-SEASONAL_PERIOD:], steps).astype(float)


def _trend_seasonal(train: np.ndarray, train_index: pd.DatetimeIndex,
                    future_index: pd.DatetimeIndex) -> np.ndarray:
    """OLS linear trend plus calendar-month fixed effects."""
    origin = train_index[0]
    t = np.asarray((train_index.year - origin.year) * 12 +
                   (train_index.month - origin.month), dtype=float)
    tf = np.asarray((future_index.year - origin.year) * 12 +
                    (future_index.month - origin.month), dtype=float)
    month = train_index.month.to_numpy()
    month_f = future_index.month.to_numpy()
    x = np.column_stack([np.ones(len(train)), t] +
                        [(month == m).astype(float) for m in range(2, 13)])
    xf = np.column_stack([np.ones(len(tf)), tf] +
                         [(month_f == m).astype(float) for m in range(2, 13)])
    beta, *_ = np.linalg.lstsq(x, train, rcond=None)
    return xf @ beta


def _predict(model: str, train: pd.Series, steps: int) -> np.ndarray:
    future_index = pd.date_range(
        train.index[-1] + pd.offsets.MonthBegin(1), periods=steps, freq="MS"
    )
    values = train.to_numpy(dtype=float)
    if model == "seasonal_naive":
        return _seasonal_naive(values, steps)
    if model == "trend_seasonal":
        return _trend_seasonal(values, train.index, future_index)
    if model == "ets_additive_damped":
        fitted = ExponentialSmoothing(
            train, trend="add", damped_trend=True, seasonal="add",
            seasonal_periods=SEASONAL_PERIOD, initialization_method="estimated"
        ).fit(optimized=True, remove_bias=False)
        return np.asarray(fitted.forecast(steps), dtype=float)
    raise ForecastError(f"Unknown forecasting model: {model}")


def _backtest(s: pd.Series, origins: int) -> tuple[pd.DataFrame, dict]:
    if origins < 3:
        raise ForecastError("At least three rolling backtest origins are required.")
    model_names = ("seasonal_naive", "trend_seasonal", "ets_additive_damped")
    rows = []
    # Each origin predicts the following 12 months. Origins are one year apart.
    for k in range(origins, 0, -1):
        cut = len(s) - 12 * k
        train, actual = s.iloc[:cut], s.iloc[cut:cut + 12]
        if len(actual) != 12 or len(train) < MIN_TRAIN_MONTHS:
            continue
        for model in model_names:
            try:
                pred = _predict(model, train, 12)
            except Exception:
                continue
            for lead, (date, observed, estimate) in enumerate(
                zip(actual.index, actual.to_numpy(), pred), start=1
            ):
                rows.append({
                    "origin": train.index[-1], "date": date, "lead_month": lead,
                    "model": model, "actual": float(observed),
                    "predicted": float(estimate), "error": float(observed - estimate),
                })
    bt = pd.DataFrame(rows)
    if bt.empty:
        raise ForecastError("No valid rolling-origin backtest could be completed.")
    counts = bt.groupby("model")["origin"].nunique()
    eligible = counts[counts >= 3].index.tolist()
    if "seasonal_naive" not in eligible:
        raise ForecastError("The seasonal-naive baseline could not be evaluated at three origins.")
    metrics = {}
    for model in eligible:
        e = bt.loc[bt.model == model, "error"].to_numpy()
        metrics[model] = {
            "mae": float(np.mean(np.abs(e))),
            "rmse": float(np.sqrt(np.mean(e ** 2))),
            "bias": float(np.mean(e)),
            "n_predictions": int(len(e)),
            "n_origins": int(counts[model]),
        }
    selected = min(eligible, key=lambda name: metrics[name]["mae"])
    baseline_mae = metrics["seasonal_naive"]["mae"]
    skill = (1 - metrics[selected]["mae"] / baseline_mae) if baseline_mae > 0 else 0.0
    return bt, {
        "selected_model": selected,
        "metrics": metrics,
        "baseline_model": "seasonal_naive",
        "skill_vs_seasonal_naive": float(skill),
        "n_origins": int(counts[selected]),
    }


def forecast_monthly(series: pd.Series, horizon_months: int = 60,
                     backtest_origins: int = DEFAULT_BACKTEST_ORIGINS,
                     lower_bound: float | None = None,
                     upper_bound: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Forecast 1-60 months ahead and return forecast rows plus transparent diagnostics.

    Model choice is based on rolling-origin 12-month MAE. The 80% and 95% bands are
    empirical, symmetric error bands calibrated from that selected model's withheld
    one-year forecasts. For leads beyond 12 months, band width expands with sqrt(h/12).
    These are approximate statistical intervals, not formal climate projection ranges.
    """
    if not 1 <= int(horizon_months) <= MAX_HORIZON_MONTHS:
        raise ForecastError(f"horizon_months must be between 1 and {MAX_HORIZON_MONTHS}.")
    s = _regular_monthly_series(series)
    bt, diagnostics = _backtest(s, int(backtest_origins))
    model = diagnostics["selected_model"]
    errors = bt.loc[bt.model == model, "error"].to_numpy(dtype=float)
    if len(errors) < 24:
        raise ForecastError(
            f"Only {len(errors)} withheld errors are available for interval calibration; "
            "at least 24 are required."
        )
    q80, q95 = np.quantile(np.abs(errors), [0.80, 0.95])
    future_index = pd.date_range(
        s.index[-1] + pd.offsets.MonthBegin(1), periods=int(horizon_months), freq="MS"
    )
    point = _predict(model, s, int(horizon_months))
    lead = np.arange(1, int(horizon_months) + 1, dtype=float)
    scale = np.sqrt(np.maximum(1.0, lead / 12.0))
    result = pd.DataFrame({
        "date": future_index,
        "lead_month": lead.astype(int),
        "forecast": point,
        "lower_80": point - q80 * scale,
        "upper_80": point + q80 * scale,
        "lower_95": point - q95 * scale,
        "upper_95": point + q95 * scale,
    })
    if lower_bound is not None:
        for col in ("forecast", "lower_80", "upper_80", "lower_95", "upper_95"):
            result[col] = result[col].clip(lower=lower_bound)
    if upper_bound is not None:
        for col in ("forecast", "lower_80", "upper_80", "lower_95", "upper_95"):
            result[col] = result[col].clip(upper=upper_bound)
    diagnostics.update({
        "training_start": s.index.min().strftime("%Y-%m"),
        "training_end": s.index.max().strftime("%Y-%m"),
        "n_training_months": int(len(s)),
        "horizon_months": int(horizon_months),
        "calibration_errors": int(len(errors)),
        "interval_method": "empirical rolling-origin absolute errors; sqrt(h/12) widening after month 12",
        "interval_warning": (
            "Approximate statistical uncertainty bands. They assume historical error behaviour "
            "remains informative and do not include future emissions, policy, land-use, or "
            "climate-model scenario uncertainty."
        ),
        "backtest": bt,
    })
    return result, diagnostics
