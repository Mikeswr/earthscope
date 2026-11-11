"""Multi-horizon real-data validation for EarthScope's experimental forecasts.

Evaluates each candidate model independently at 12, 24, 36 and 60 months
using expanding-window rolling origins. Only genuine NASA POWER rows with
qc_flag == 'ok' are eligible. No interpolation or synthetic data are used.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecasting.engine import (  # noqa: E402
    MIN_TRAIN_MONTHS, ForecastError, _predict, _regular_monthly_series,
)

DATA = ROOT / "data" / "processed" / "power_monthly_standardised.csv"
OUT = ROOT / "reports" / "forecast_validation"
HORIZONS = (12, 24, 36, 60)
ORIGINS = 5
MODELS = ("seasonal_naive", "trend_seasonal", "ets_additive_damped")
EXPECTED_VARIABLES = {
    "T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS10M",
    "ALLSKY_SFC_SW_DWN",
}


def rolling_evaluate(series: pd.Series, horizon: int) -> list[dict]:
    rows = []
    # Origins are 12 months apart, with the same horizon-specific lead window.
    for offset in range(ORIGINS - 1, -1, -1):
        cut = len(series) - horizon - offset * 12
        train = series.iloc[:cut]
        actual = series.iloc[cut:cut + horizon]
        if len(actual) != horizon or len(train) < MIN_TRAIN_MONTHS:
            continue
        for model in MODELS:
            try:
                predicted = _predict(model, train, horizon)
                if len(predicted) != horizon or not np.isfinite(predicted).all():
                    continue
            except Exception as exc:
                rows.append({
                    "horizon_months": horizon, "origin": train.index[-1].strftime("%Y-%m"),
                    "model": model, "status": "model_error", "reason": str(exc)[:240],
                })
                continue
            errors = actual.to_numpy(dtype=float) - predicted
            for lead, (date, observed, estimate, error) in enumerate(
                zip(actual.index, actual.to_numpy(dtype=float), predicted, errors), start=1
            ):
                rows.append({
                    "horizon_months": horizon,
                    "origin": train.index[-1].strftime("%Y-%m"),
                    "date": date.strftime("%Y-%m"),
                    "lead_month": lead,
                    "model": model,
                    "actual": float(observed),
                    "predicted": float(estimate),
                    "error": float(error),
                    "status": "ok",
                })
    return rows


def main() -> int:
    if not DATA.exists():
        raise FileNotFoundError(f"Processed NASA POWER dataset not found: {DATA}")
    df = pd.read_csv(DATA, parse_dates=["date"])
    required = {"date", "location", "variable", "value", "unit", "source", "data_kind", "qc_flag"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Processed dataset is missing columns: {sorted(missing)}")

    real = df[
        (df["source"] == "NASA POWER")
        & (df["data_kind"] == "gridded_estimate_not_station_observation")
    ].copy()
    if real.empty:
        raise ValueError("No genuine NASA POWER observations found; synthetic data are excluded.")
    variables = sorted(real["variable"].dropna().unique())
    unexpected = set(variables).difference(EXPECTED_VARIABLES)
    if unexpected:
        raise ValueError(f"Unexpected variables: {sorted(unexpected)}")
    locations = sorted(real["location"].dropna().unique())

    summary_rows, detail_rows = [], []
    expected_pairs = [(loc, var) for loc in locations for var in sorted(EXPECTED_VARIABLES)]
    for location, variable in expected_pairs:
        group = real[(real.location == location) & (real.variable == variable)].sort_values("date")
        if group.empty:
            for horizon in HORIZONS:
                summary_rows.append({
                    "location": location, "variable": variable, "horizon_months": horizon,
                    "status": "missing_series", "reason": "No matching NASA POWER series.",
                })
            continue
        if group["date"].duplicated().any():
            for horizon in HORIZONS:
                summary_rows.append({
                    "location": location, "variable": variable, "horizon_months": horizon,
                    "status": "duplicate_dates", "reason": "Duplicate monthly dates.",
                })
            continue

        # Keep the complete calendar. QC-invalid and missing values remain gaps.
        values = group["value"].where(group["qc_flag"] == "ok")
        raw_series = pd.Series(values.to_numpy(dtype=float), index=pd.DatetimeIndex(group["date"]))
        try:
            series = _regular_monthly_series(raw_series)
        except ForecastError as exc:
            for horizon in HORIZONS:
                summary_rows.append({
                    "location": location, "variable": variable, "horizon_months": horizon,
                    "status": "not_forecastable", "n_valid_months": int(values.notna().sum()),
                    "reason": str(exc),
                })
            continue

        for horizon in HORIZONS:
            rows = rolling_evaluate(series, horizon)
            valid = [row for row in rows if row.get("status") == "ok"]
            detail_rows.extend({
                "location": location, "variable": variable, **row
            } for row in rows)
            if not valid:
                summary_rows.append({
                    "location": location, "variable": variable, "horizon_months": horizon,
                    "status": "insufficient_origins", "n_training_months": len(series),
                    "reason": "No valid rolling-origin predictions at this horizon.",
                })
                continue
            valid_df = pd.DataFrame(valid)
            metrics = {}
            for model, model_df in valid_df.groupby("model"):
                errors = model_df["error"].to_numpy(dtype=float)
                n_origins = int(model_df["origin"].nunique())
                metrics[model] = {
                    "mae": float(np.mean(np.abs(errors))),
                    "rmse": float(np.sqrt(np.mean(errors ** 2))),
                    "bias": float(np.mean(errors)),
                    "n_predictions": int(len(errors)),
                    "n_origins": n_origins,
                }
            eligible = {m: v for m, v in metrics.items() if v["n_origins"] >= 3}
            if "seasonal_naive" not in eligible:
                summary_rows.append({
                    "location": location, "variable": variable, "horizon_months": horizon,
                    "status": "insufficient_baseline", "n_training_months": len(series),
                    "reason": "Seasonal-naive baseline did not complete at least three origins.",
                })
                continue
            selected = min(eligible, key=lambda model: eligible[model]["mae"])
            baseline_mae = eligible["seasonal_naive"]["mae"]
            selected_metrics = eligible[selected]
            skill = 1 - selected_metrics["mae"] / baseline_mae if baseline_mae > 0 else 0.0
            summary_rows.append({
                "location": location, "variable": variable, "unit": group["unit"].iloc[0],
                "horizon_months": horizon, "status": "evaluated",
                "training_start": series.index.min().strftime("%Y-%m"),
                "training_end": series.index.max().strftime("%Y-%m"),
                "n_training_months": len(series), "selected_model": selected,
                "mae": selected_metrics["mae"], "rmse": selected_metrics["rmse"],
                "bias": selected_metrics["bias"], "baseline_mae": baseline_mae,
                "skill_vs_seasonal_naive": skill,
                "n_origins": selected_metrics["n_origins"],
                "n_predictions": selected_metrics["n_predictions"],
                "candidate_metrics_json": json.dumps(eligible, sort_keys=True),
                "reason": "",
            })

    OUT.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(summary_rows).sort_values(
        ["location", "variable", "horizon_months"]
    )
    details = pd.DataFrame(detail_rows)
    summary.to_csv(OUT / "forecast_validation_results.csv", index=False)
    details.to_csv(OUT / "forecast_validation_predictions.csv", index=False)

    evaluated = summary[summary.status == "evaluated"]
    report = [
        "# EarthScope multi-horizon real-data forecast validation", "",
        "## Validation design", "",
        f"- Genuine NASA POWER rows: {len(real):,}.",
        f"- Locations: {len(locations)} ({', '.join(locations)}).",
        f"- Variables: {len(variables)} ({', '.join(variables)}).",
        f"- Expected location-variable combinations: {len(expected_pairs)}.",
        f"- Forecast horizons evaluated independently: {', '.join(map(str, HORIZONS))} months.",
        f"- Rolling origins: up to {ORIGINS}, spaced 12 months apart for each horizon.",
        "- Candidate methods: seasonal naive, linear trend plus calendar-month effects, and damped additive ETS.",
        "- Selection: lowest pooled MAE at the same horizon being evaluated.",
        "- Eligibility: NASA POWER source, documented gridded-estimate data kind, and qc_flag == 'ok'.",
        "- Missing months and QC-invalid observations are not interpolated.",
        "", "## Results by horizon", "",
    ]
    for horizon in HORIZONS:
        subset = summary[summary.horizon_months == horizon]
        good = subset[subset.status == "evaluated"]
        better = int((good.skill_vs_seasonal_naive > 0).sum())
        report += [
            f"### {horizon}-month horizon",
            f"- Evaluated: {len(good)} of {len(expected_pairs)} combinations.",
            f"- Selected model beats seasonal-naive: {better} of {len(good)} evaluated combinations.",
            f"- Not evaluated: {len(subset) - len(good)}.",
            "",
        ]
    report += [
        "## Combination-level results", "",
        summary.to_markdown(index=False), "",
        "## Interpretation", "",
        "A horizon is supported only by its own rolling-origin evaluation. Good 12-month performance is not evidence of 60-month skill. Positive skill means the selected candidate has lower MAE than seasonal-naive at that same horizon. These are statistical extrapolations of NASA POWER point series, not scenario-based climate projections. The backtest uses historical conditions and cannot account for future emissions, policy, land-use change or structural shifts.",
        "",
        "This validation assesses point-forecast error. It does not yet validate the dashboard's forecast uncertainty bands. Do not describe the 80% or 95% bands as calibrated coverage until interval coverage has been separately evaluated.",
        "",
    ]
    (OUT / "FORECAST_VALIDATION_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
