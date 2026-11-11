"""Run real-data validation of EarthScope's experimental forecasts.

Reads only committed, processed NASA POWER observations. Synthetic records are excluded.
Writes a machine-readable validation table, monthly forecast table and Markdown summary.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

from forecasting.engine import ForecastError, forecast_monthly

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "power_monthly_standardised.csv"
OUT = ROOT / "reports" / "forecast_validation"
EXPECTED_VARIABLES = {
    "T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS10M",
    "ALLSKY_SFC_SW_DWN",
}
BOUNDS = {
    "PRECTOTCORR": (0.0, None),
    "RH2M": (0.0, 100.0),
    "WS10M": (0.0, None),
    "ALLSKY_SFC_SW_DWN": (0.0, None),
}


def main() -> int:
    if not DATA.exists():
        raise FileNotFoundError(f"Processed NASA POWER dataset not found: {DATA}")
    df = pd.read_csv(DATA, parse_dates=["date"])
    required = {"location", "date", "variable", "value", "unit", "source", "data_kind", "qc_flag"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Processed dataset is missing columns: {sorted(missing)}")

    # Strictly exclude synthetic data and any non-NASA source.
    real = df[(df["source"] == "NASA POWER") &
              (df["data_kind"] == "gridded_estimate_not_station_observation")].copy()
    if real.empty:
        raise ValueError("No genuine NASA POWER rows were found. Synthetic data are not eligible.")
    locations = sorted(real["location"].dropna().unique())
    variables = sorted(real["variable"].dropna().unique())
    unexpected = set(variables).difference(EXPECTED_VARIABLES)
    if unexpected:
        raise ValueError(f"Unexpected variables in dataset: {sorted(unexpected)}")

    results, forecasts = [], []
    for location in locations:
        for variable in variables:
            g = real[(real["location"] == location) & (real["variable"] == variable)].copy()
            if g.empty:
                continue
            g = g.sort_values("date")
            if g["date"].duplicated().any():
                results.append({
                    "location": location, "variable": variable, "unit": g["unit"].iloc[0],
                    "status": "FAILED_DATA_CHECK", "reason": "Duplicate monthly dates",
                })
                continue
            # Preserve the calendar. Any non-OK QC row becomes missing and is not interpolated.
            values = g["value"].where(g["qc_flag"] == "ok")
            series = pd.Series(values.to_numpy(dtype=float), index=pd.DatetimeIndex(g["date"]))
            lower, upper = BOUNDS.get(variable, (None, None))
            try:
                fc, info = forecast_monthly(series, horizon_months=60,
                                            backtest_origins=5,
                                            lower_bound=lower, upper_bound=upper)
                selected = info["selected_model"]
                selected_metrics = info["metrics"][selected]
                baseline = info["metrics"]["seasonal_naive"]
                skill = info["skill_vs_seasonal_naive"]
                if selected == "seasonal_naive":
                    verdict = "BASELINE_BEST"
                elif skill > 0:
                    verdict = "BEATS_BASELINE"
                else:
                    verdict = "NO_BASELINE_IMPROVEMENT"
                results.append({
                    "location": location, "variable": variable, "unit": g["unit"].iloc[0],
                    "status": "FORECASTED", "verdict": verdict,
                    "training_start": info["training_start"], "training_end": info["training_end"],
                    "training_months": info["n_training_months"],
                    "selected_model": selected,
                    "mae": selected_metrics["mae"], "rmse": selected_metrics["rmse"],
                    "bias": selected_metrics["bias"],
                    "baseline_mae": baseline["mae"], "baseline_rmse": baseline["rmse"],
                    "skill_vs_baseline": skill,
                    "backtest_origins": info["n_origins"],
                    "calibration_errors": info["calibration_errors"],
                    "forecast_start": fc["date"].min().strftime("%Y-%m"),
                    "forecast_end": fc["date"].max().strftime("%Y-%m"),
                    "reason": "",
                })
                fc.insert(0, "variable", variable)
                fc.insert(0, "location", location)
                fc.insert(0, "unit", g["unit"].iloc[0])
                fc["selected_model"] = selected
                forecasts.append(fc)
            except ForecastError as exc:
                results.append({
                    "location": location, "variable": variable, "unit": g["unit"].iloc[0],
                    "status": "NOT_FORECASTABLE", "verdict": "NOT_ASSESSED",
                    "training_start": "", "training_end": "",
                    "training_months": int(values.notna().sum()),
                    "selected_model": "", "mae": None, "rmse": None, "bias": None,
                    "baseline_mae": None, "baseline_rmse": None, "skill_vs_baseline": None,
                    "backtest_origins": 0, "calibration_errors": 0,
                    "forecast_start": "", "forecast_end": "", "reason": str(exc),
                })

    OUT.mkdir(parents=True, exist_ok=True)
    result_df = pd.DataFrame(results).sort_values(["location", "variable"])
    result_df.to_csv(OUT / "forecast_validation_results.csv", index=False)
    if forecasts:
        pd.concat(forecasts, ignore_index=True).to_csv(OUT / "monthly_forecasts_60_months.csv", index=False)

    counts = result_df["status"].value_counts().to_dict()
    verdicts = result_df.loc[result_df["status"] == "FORECASTED", "verdict"].value_counts().to_dict()
    report = [
        "# EarthScope real-data forecasting validation",
        "",
        "## Scope",
        "",
        f"- Source: committed NASA POWER monthly processed dataset ({len(real):,} rows).",
        f"- Locations: {len(locations)} ({', '.join(locations)}).",
        f"- Variables: {len(variables)} ({', '.join(variables)}).",
        f"- Candidate location-variable series: {len(result_df)}.",
        "- Synthetic and non-NASA rows were excluded.",
        "- Forecast horizon: 60 monthly steps (five years).",
        "- Model selection: five expanding-window rolling origins, each predicting the next 12 months.",
        "- Selection metric: pooled one-year backtest MAE; seasonal-naive is the baseline.",
        "- Missing or QC-invalid internal months are not interpolated.",
        "",
        "## Outcomes",
        "",
        f"- Forecasted series: {counts.get('FORECASTED', 0)}.",
        f"- Not forecastable: {counts.get('NOT_FORECASTABLE', 0)}.",
        f"- Data-check failures: {counts.get('FAILED_DATA_CHECK', 0)}.",
        f"- Forecast verdicts: {json.dumps(verdicts, sort_keys=True)}.",
        "",
        "## Series-level results",
        "",
        result_df.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "A forecast being generated does not establish that it is reliable. BEATS_BASELINE means the selected candidate had lower pooled 12-month backtest MAE than the seasonal-naive baseline. BASELINE_BEST means the seasonal-naive model was selected. NO_BASELINE_IMPROVEMENT means a selected candidate did not show positive skill under the reported comparison. These are point-series statistical extrapolations, not scenario-based climate projections.",
        "",
        "The empirical 80% and 95% bands are approximate, calibrated from withheld absolute errors. They are not formal probabilistic guarantees and do not account for future emissions, policy, land-use or climate-model scenario uncertainty. This report does not establish forecast skill beyond the tested backtest design.",
        "",
    ]
    (OUT / "FORECAST_VALIDATION_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    (OUT / "forecast_validation_summary.json").write_text(json.dumps({
        "rows": len(real), "locations": locations, "variables": variables,
        "candidate_series": len(result_df), "status_counts": counts,
        "verdict_counts": verdicts,
    }, indent=2), encoding="utf-8")
    print((OUT / "FORECAST_VALIDATION_REPORT.md").read_text(encoding="utf-8"))
    return 0 if counts.get("FAILED_DATA_CHECK", 0) == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
