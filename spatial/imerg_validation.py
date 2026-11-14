"""Cross-product consistency assessment for NASA POWER and GPM IMERG precipitation.

The comparison matches monthly values on approximate POWER grid-cell supports.
It is not independent station validation: POWER PRECTOTCORR and IMERG Final
both incorporate observational precipitation information through different
processing pathways.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

IMERG_COLLECTION = "NASA/GPM_L3/IMERG_MONTHLY_V07"
IMERG_DOI = "10.5067/GPM/IMERG/3B-MONTH/07"
DEFAULT_START = "1998-01-01"
DEFAULT_END = "2025-09-01"

GRID_REQUIRED = {
    "cell_id", "latitude", "longitude",
    "latitude_spacing_degrees", "longitude_spacing_degrees",
}
POWER_REQUIRED = {"date", "variable", "value", "latitude", "longitude", "cell_id", "unit"}
IMERG_REQUIRED = {
    "date", "cell_id", "latitude", "longitude",
    "precipitation_mean", "precipitation_count",
}


def _month_index(start, end):
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="MS")


def _safe_corr(x, y, method="pearson"):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    if method == "pearson":
        return float(np.corrcoef(x, y)[0, 1])
    result = spearmanr(x, y)
    return float(result.statistic) if np.isfinite(result.statistic) else np.nan


def _metrics(power, imerg):
    power = np.asarray(power, dtype=float)
    imerg = np.asarray(imerg, dtype=float)
    ok = np.isfinite(power) & np.isfinite(imerg)
    p, g = power[ok], imerg[ok]
    n = int(len(p))
    if not n:
        return {
            "n_pairs": 0, "power_mean_mm": np.nan, "imerg_mean_mm": np.nan,
            "bias_imerg_minus_power_mm": np.nan, "mae_mm": np.nan, "rmse_mm": np.nan,
            "ubrmse_mm": np.nan, "pbias_percent": np.nan,
            "pearson_r": np.nan, "spearman_r": np.nan, "nse": np.nan,
        }
    diff = g - p
    bias = float(np.mean(diff))
    denom = float(np.sum(p))
    variance = float(np.sum((p - np.mean(p)) ** 2))
    nse = 1.0 - float(np.sum(diff ** 2)) / variance if variance > 0 else np.nan
    return {
        "n_pairs": n,
        "power_mean_mm": float(np.mean(p)),
        "imerg_mean_mm": float(np.mean(g)),
        "bias_imerg_minus_power_mm": bias,
        "mae_mm": float(np.mean(np.abs(diff))),
        "rmse_mm": float(np.sqrt(np.mean(diff ** 2))),
        "ubrmse_mm": float(np.sqrt(np.mean((diff - bias) ** 2))),
        "pbias_percent": float(100.0 * np.sum(diff) / denom) if denom > 0 else np.nan,
        "pearson_r": _safe_corr(p, g, "pearson"),
        "spearman_r": _safe_corr(p, g, "spearman"),
        "nse": nse,
    }


def _validate_grid(grid):
    missing = GRID_REQUIRED - set(grid.columns)
    if missing:
        raise ValueError("POWER grid reference is missing columns: " + ", ".join(sorted(missing)))
    g = grid.copy()
    g["latitude"] = pd.to_numeric(g["latitude"], errors="coerce")
    g["longitude"] = pd.to_numeric(g["longitude"], errors="coerce")
    if g["cell_id"].isna().any() or g["cell_id"].duplicated().any():
        raise ValueError("POWER grid reference must contain unique, non-empty cell IDs.")
    if g[["latitude", "longitude"]].isna().any(axis=None):
        raise ValueError("POWER grid reference contains invalid coordinates.")
    if g["latitude"].abs().gt(90).any() or g["longitude"].abs().gt(180).any():
        raise ValueError("POWER grid reference coordinates fall outside valid geographic ranges.")
    return g


def _validate_power(power, grid, start, end):
    missing = POWER_REQUIRED - set(power.columns)
    if missing:
        raise ValueError("POWER precipitation input is missing columns: " + ", ".join(sorted(missing)))
    p = power.loc[power["variable"].eq("PRECTOTCORR")].copy()
    if p.empty:
        raise ValueError("No PRECTOTCORR records were found in the POWER input.")
    p["date"] = pd.to_datetime(p["date"], errors="coerce")
    p["value"] = pd.to_numeric(p["value"], errors="coerce")
    p["latitude"] = pd.to_numeric(p["latitude"], errors="coerce")
    p["longitude"] = pd.to_numeric(p["longitude"], errors="coerce")
    if p["date"].isna().any() or not p["date"].dt.is_month_start.all():
        raise ValueError("POWER dates must be valid month-start timestamps.")
    p = p[p["date"].between(start, end)]
    if p.duplicated(["cell_id", "date"]).any():
        raise ValueError("POWER input contains duplicate cell-month records.")
    units = sorted(p["unit"].dropna().astype(str).unique())
    if units != ["mm/day"]:
        raise ValueError(f"PRECTOTCORR must be in mm/day; found units: {units}")
    if p["value"].dropna().lt(0).any():
        raise ValueError("POWER PRECTOTCORR contains negative precipitation rates.")

    expected = set(grid["cell_id"])
    actual = set(p["cell_id"].dropna())
    if not expected.issubset(actual):
        missing_cells = sorted(expected - actual)
        raise ValueError("POWER data lack expected grid cells: " + ", ".join(missing_cells[:10]))
    p = p[p["cell_id"].isin(expected)].copy()
    coordinates = grid.set_index("cell_id")[["latitude", "longitude"]]
    p = p.merge(
        coordinates.reset_index(), on="cell_id", how="left",
        validate="many_to_one", suffixes=("", "_grid")
    )
    coord_mismatch = (
        (p["latitude"] - p["latitude_grid"]).abs().gt(1e-4)
        | (p["longitude"] - p["longitude_grid"]).abs().gt(1e-4)
    )
    if coord_mismatch.any():
        raise ValueError("POWER CSV coordinates do not match the stored grid reference.")
    p["days_in_month"] = p["date"].dt.days_in_month
    p["power_daily_rate_mm_day"] = p["value"]
    p["power_month_total_mm"] = p["value"] * p["days_in_month"]
    return p.drop(columns=["latitude_grid", "longitude_grid"])


def _validate_imerg(imerg, grid, start, end):
    missing = IMERG_REQUIRED - set(imerg.columns)
    if missing:
        raise ValueError("IMERG export is missing columns: " + ", ".join(sorted(missing)))
    g = imerg.copy()
    g["date"] = pd.to_datetime(g["date"], errors="coerce")
    for col in [
        "latitude", "longitude", "precipitation_mean", "precipitation_count",
        "gaugeRelativeWeighting_mean", "precipitationQualityIndex_mean",
        "randomError_mean", "imerg_month_hours",
        "imerg_precipitation_mm_month_total",
    ]:
        if col in g:
            g[col] = pd.to_numeric(g[col], errors="coerce")
    if g["date"].isna().any() or not g["date"].dt.is_month_start.all():
        raise ValueError("IMERG dates must be valid month-start timestamps.")
    g = g[g["date"].between(start, end)].copy()
    if g.duplicated(["cell_id", "date"]).any():
        raise ValueError("IMERG export contains duplicate cell-month records.")
    expected = set(grid["cell_id"])
    unexpected = sorted(set(g["cell_id"].dropna()) - expected)
    if unexpected:
        raise ValueError("IMERG export contains cell IDs outside the reference grid: " + ", ".join(unexpected[:10]))
    if not set(grid["cell_id"]).issubset(set(g["cell_id"].dropna())):
        absent = sorted(set(grid["cell_id"]) - set(g["cell_id"].dropna()))
        raise ValueError("IMERG export is missing reference cells: " + ", ".join(absent[:10]))
    coordinates = grid.set_index("cell_id")[["latitude", "longitude"]]
    g = g.merge(
        coordinates.reset_index(), on="cell_id", how="left",
        validate="many_to_one", suffixes=("", "_grid")
    )
    coord_mismatch = (
        (g["latitude"] - g["latitude_grid"]).abs().gt(1e-4)
        | (g["longitude"] - g["longitude_grid"]).abs().gt(1e-4)
    )
    if coord_mismatch.any():
        raise ValueError("IMERG export coordinates do not match the POWER support grid.")
    if g["precipitation_mean"].dropna().lt(0).any():
        raise ValueError("IMERG precipitation contains negative precipitation rates.")
    if g["precipitation_count"].dropna().lt(0).any():
        raise ValueError("IMERG valid-pixel counts cannot be negative.")
    populated = g["precipitation_mean"].notna()
    if (g.loc[populated, "precipitation_count"].fillna(0) <= 0).any():
        raise ValueError("IMERG contains a precipitation mean with zero or missing pixel count.")

    g["days_in_month"] = g["date"].dt.days_in_month
    g["expected_month_hours"] = g["days_in_month"] * 24.0
    g["imerg_daily_rate_mm_day"] = g["precipitation_mean"] * 24.0
    g["imerg_month_total_mm"] = g["precipitation_mean"] * g["expected_month_hours"]
    if "imerg_month_hours" in g:
        supplied = g["imerg_month_hours"].notna()
        hour_mismatch = (
            g.loc[supplied, "imerg_month_hours"]
            .sub(g.loc[supplied, "expected_month_hours"]).abs().gt(1e-6)
        )
        if hour_mismatch.any():
            raise ValueError("IMERG export month-hours do not match the calendar month.")
    if "imerg_precipitation_mm_month_total" in g:
        supplied = g["imerg_precipitation_mm_month_total"].notna() & g["imerg_month_total_mm"].notna()
        delta = (
            g.loc[supplied, "imerg_precipitation_mm_month_total"]
            - g.loc[supplied, "imerg_month_total_mm"]
        ).abs()
        if delta.gt(0.05).any():
            raise ValueError("Exported IMERG monthly totals do not match rate-to-total conversion.")
    return g.drop(columns=["latitude_grid", "longitude_grid"])


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    return value


def compare_power_imerg(
    power_frame,
    imerg_frame,
    grid_frame,
    start=DEFAULT_START,
    end=DEFAULT_END,
    minimum_cell_coverage=0.80,
):
    """Compare monthly POWER and IMERG precipitation on matched approximate grid support.

    All comparisons are pairwise-complete. Missing observations are not filled.
    IMERG Final is gauge adjusted; this is cross-product consistency analysis,
    not independent station validation.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.day != 1 or end.day != 1 or start > end:
        raise ValueError("start and end must be ordered month-start dates.")
    if not 0 < minimum_cell_coverage <= 1:
        raise ValueError("minimum_cell_coverage must be in (0, 1].")
    expected_months = _month_index(start, end)
    grid = _validate_grid(grid_frame)
    power = _validate_power(power_frame, grid, start, end)
    imerg = _validate_imerg(imerg_frame, grid, start, end)

    expected_rows = len(grid) * len(expected_months)
    coverage_rows = []
    for cell_id in grid["cell_id"]:
        group = imerg.loc[imerg["cell_id"].eq(cell_id)]
        valid = group["precipitation_mean"].notna() & group["precipitation_count"].fillna(0).gt(0)
        coverage_rows.append({
            "cell_id": cell_id,
            "expected_months": int(len(expected_months)),
            "exported_month_rows": int(len(group)),
            "valid_months": int(valid.sum()),
            "valid_month_coverage": float(valid.sum() / len(expected_months)) if len(expected_months) else np.nan,
            "median_valid_imerg_pixels": float(group.loc[valid, "precipitation_count"].median()) if valid.any() else np.nan,
            "eligible_at_coverage_threshold": bool(valid.sum() / len(expected_months) >= minimum_cell_coverage),
        })
    coverage = pd.DataFrame(coverage_rows)

    p = power[[
        "date", "cell_id", "latitude", "longitude",
        "power_daily_rate_mm_day", "power_month_total_mm",
    ]]
    gcols = [
        "date", "cell_id", "latitude", "longitude",
        "precipitation_mean", "precipitation_count",
        "imerg_daily_rate_mm_day", "imerg_month_total_mm",
    ]
    for optional in [
        "gaugeRelativeWeighting_mean",
        "precipitationQualityIndex_mean",
        "randomError_mean",
        "imerg_collection_status",
    ]:
        if optional in imerg.columns:
            gcols.append(optional)
    paired = p.merge(
        imerg[gcols], on=["date", "cell_id"], how="inner",
        suffixes=("_power", "_imerg"), validate="one_to_one",
    )
    valid = (
        paired["power_month_total_mm"].notna()
        & paired["imerg_month_total_mm"].notna()
        & paired["precipitation_count"].fillna(0).gt(0)
    )
    paired = paired.loc[valid].copy()
    if paired.empty:
        raise ValueError("No valid paired POWER and IMERG monthly observations are available.")

    metrics_rows = []
    for cell_id, group in paired.groupby("cell_id"):
        grid_row = grid.loc[grid["cell_id"].eq(cell_id)].iloc[0]
        met = _metrics(group["power_month_total_mm"], group["imerg_month_total_mm"])
        coverage_row = coverage.loc[coverage["cell_id"].eq(cell_id)].iloc[0]
        metrics_rows.append({
            "cell_id": cell_id,
            "latitude": float(grid_row["latitude"]),
            "longitude": float(grid_row["longitude"]),
            "valid_month_coverage": float(coverage_row["valid_month_coverage"]),
            "eligible_at_coverage_threshold": bool(coverage_row["eligible_at_coverage_threshold"]),
            "median_valid_imerg_pixels": coverage_row["median_valid_imerg_pixels"],
            **met,
        })
    cell_metrics = pd.DataFrame(metrics_rows).sort_values(["latitude", "longitude"]).reset_index(drop=True)

    paired["month_number"] = paired["date"].dt.month
    paired["season"] = paired["month_number"].map({
        12: "DJF", 1: "DJF", 2: "DJF",
        3: "MAM", 4: "MAM", 5: "MAM",
        6: "JJA", 7: "JJA", 8: "JJA",
        9: "SON", 10: "SON", 11: "SON",
    })
    season_rows = []
    for (cell_id, season), group in paired.groupby(["cell_id", "season"]):
        met = _metrics(group["power_month_total_mm"], group["imerg_month_total_mm"])
        season_rows.append({"cell_id": cell_id, "season": season, **met})
    seasonal_metrics = pd.DataFrame(season_rows).sort_values(["cell_id", "season"]).reset_index(drop=True)

    anomaly_rows = []
    for cell_id, group in paired.groupby("cell_id"):
        group = group.copy()
        for source_col, out_col in [
            ("power_month_total_mm", "power_z"),
            ("imerg_month_total_mm", "imerg_z"),
        ]:
            means = group.groupby("month_number")[source_col].transform("mean")
            stds = group.groupby("month_number")[source_col].transform("std")
            group[out_col] = (group[source_col] - means) / stds.replace(0, np.nan)
        anomaly_rows.append({
            "cell_id": cell_id,
            "n_standardised_month_pairs": int(group[["power_z", "imerg_z"]].dropna().shape[0]),
            "standardised_monthly_anomaly_pearson_r": _safe_corr(group["power_z"], group["imerg_z"]),
            "power_monthly_total_mean_mm": float(group["power_month_total_mm"].mean()),
            "imerg_monthly_total_mean_mm": float(group["imerg_month_total_mm"].mean()),
        })
    anomaly_metrics = pd.DataFrame(anomaly_rows)

    annual_rows = []
    paired["year"] = paired["date"].dt.year
    for (cell_id, year), group in paired.groupby(["cell_id", "year"]):
        if len(group) == 12 and group["date"].dt.month.nunique() == 12:
            annual_rows.append({
                "cell_id": cell_id,
                "year": int(year),
                "n_paired_months": 12,
                "power_annual_total_mm": float(group["power_month_total_mm"].sum()),
                "imerg_annual_total_mm": float(group["imerg_month_total_mm"].sum()),
                "bias_imerg_minus_power_mm": float(
                    group["imerg_month_total_mm"].sum() - group["power_month_total_mm"].sum()
                ),
            })
    annual_pairs = pd.DataFrame(annual_rows)

    pooled = _metrics(paired["power_month_total_mm"], paired["imerg_month_total_mm"])
    overall = {
        "n_reference_cells": int(len(grid)),
        "n_expected_cell_months": int(expected_rows),
        "n_imerg_export_rows": int(len(imerg)),
        "n_valid_paired_cell_months": int(len(paired)),
        "paired_coverage_fraction": float(len(paired) / expected_rows) if expected_rows else None,
        "period_start": start.strftime("%Y-%m"),
        "period_end": end.strftime("%Y-%m"),
        "pooled_all_cell_month_metrics_descriptive_only": pooled,
        "median_cell_pearson_r": float(cell_metrics["pearson_r"].median()),
        "median_cell_mae_mm": float(cell_metrics["mae_mm"].median()),
        "median_cell_rmse_mm": float(cell_metrics["rmse_mm"].median()),
        "cells_meeting_coverage_threshold": int(coverage["eligible_at_coverage_threshold"].sum()),
        "median_valid_imerg_pixels_per_cell_month": float(
            imerg.loc[imerg["precipitation_mean"].notna(), "precipitation_count"].median()
        ),
    }
    quality_summary = {
        "valid_months_by_cell": coverage.to_dict(orient="records"),
        "median_gauge_relative_weighting_pct": (
            float(imerg["gaugeRelativeWeighting_mean"].median())
            if "gaugeRelativeWeighting_mean" in imerg else None
        ),
        "median_precipitation_quality_index": (
            float(imerg["precipitationQualityIndex_mean"].median())
            if "precipitationQualityIndex_mean" in imerg else None
        ),
        "median_random_error_mm_per_hour": (
            float(imerg["randomError_mean"].median())
            if "randomError_mean" in imerg else None
        ),
        "quality_metrics_are_diagnostics_not_automatic_exclusion_rules": True,
    }
    eligible = bool(
        len(cell_metrics) == len(grid)
        and coverage["eligible_at_coverage_threshold"].all()
        and overall["paired_coverage_fraction"] >= minimum_cell_coverage
    )
    metadata = {
        "analysis": "monthly precipitation cross-product consistency assessment",
        "power_product": "NASA POWER PRECTOTCORR monthly, MERRA-2-based bias-corrected precipitation",
        "power_units": "mm/day converted to monthly accumulation by calendar days",
        "imerg_product": "NASA GPM IMERG Final monthly V07",
        "imerg_collection_id": IMERG_COLLECTION,
        "imerg_doi": IMERG_DOI,
        "imerg_band": "precipitation",
        "imerg_band_units": "mm/hr, converted to monthly accumulation by actual calendar hours",
        "imerg_spatial_resolution": "approximately 0.1 degree / 11,132 m",
        "spatial_matching": "area mean over approximate POWER cell rectangles inferred from returned grid-centre spacing",
        "power_cell_geometry_caveat": "rectangles are approximate and not official NASA POWER cell polygons",
        "period": {"start": start.strftime("%Y-%m"), "end": end.strftime("%Y-%m")},
        "expected_months": int(len(expected_months)),
        "minimum_cell_coverage": float(minimum_cell_coverage),
        "missing_data": "pairwise deletion only; no interpolation or imputation",
        "interpretation": (
            "Cross-product consistency assessment, not independent station validation. "
            "IMERG Final uses monthly GPCC gauge adjustment. POWER PRECTOTCORR uses "
            "observation-corrected MERRA-2 precipitation forcing, with CMAP gauge-satellite "
            "precipitation forcing over continental Africa."
        ),
        "analysis_eligible": eligible,
        "overall": overall,
        "quality_diagnostics": quality_summary,
    }
    return {
        "paired_monthly": paired.sort_values(["cell_id", "date"]).reset_index(drop=True),
        "cell_metrics": cell_metrics,
        "seasonal_metrics": seasonal_metrics,
        "standardised_anomaly_metrics": anomaly_metrics,
        "complete_annual_pairs": annual_pairs,
        "coverage": coverage,
        "metadata": metadata,
    }


def write_imerg_comparison(result, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    tables = {
        "imerg_power_monthly_pairs.csv": "paired_monthly",
        "imerg_power_cell_metrics.csv": "cell_metrics",
        "imerg_power_seasonal_metrics.csv": "seasonal_metrics",
        "imerg_power_standardised_anomaly_metrics.csv": "standardised_anomaly_metrics",
        "imerg_power_complete_annual_pairs.csv": "complete_annual_pairs",
        "imerg_power_cell_coverage.csv": "coverage",
    }
    for filename, key in tables.items():
        path = out / filename
        result[key].to_csv(path, index=False)
        files[key] = {"file": filename, "rows": int(len(result[key]))}
    meta_path = out / "imerg_power_comparison_metadata.json"
    meta_path.write_text(
        json.dumps(_json_safe(result["metadata"]), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    files["metadata"] = {"file": meta_path.name}
    report_path = out / "imerg_power_comparison_report.md"
    _write_markdown_report(result["metadata"], report_path)
    files["report"] = {"file": report_path.name}
    return files


def _fmt(value, digits=3):
    return "NA" if value is None or not np.isfinite(value) else f"{value:.{digits}f}"


def _write_markdown_report(metadata, path):
    overall = metadata["overall"]
    pooled = overall["pooled_all_cell_month_metrics_descriptive_only"]
    lines = [
        "# EarthScope precipitation cross-product assessment",
        "",
        f"**Period:** {metadata['period']['start']} to {metadata['period']['end']}",
        f"**Reference grid cells:** {overall['n_reference_cells']}",
        f"**Valid paired cell-months:** {overall['n_valid_paired_cell_months']:,} of {overall['n_expected_cell_months']:,}",
        "",
        "## Pooled descriptive metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| POWER mean monthly total (mm) | {_fmt(pooled['power_mean_mm'])} |",
        f"| IMERG mean monthly total (mm) | {_fmt(pooled['imerg_mean_mm'])} |",
        f"| Bias, IMERG minus POWER (mm) | {_fmt(pooled['bias_imerg_minus_power_mm'])} |",
        f"| MAE (mm) | {_fmt(pooled['mae_mm'])} |",
        f"| RMSE (mm) | {_fmt(pooled['rmse_mm'])} |",
        f"| Pearson r | {_fmt(pooled['pearson_r'])} |",
        f"| Spearman r | {_fmt(pooled['spearman_r'])} |",
        "",
        "These pooled cell-month metrics are descriptive. They are not based on independent samples because months are serially dependent and nearby grid cells are spatially dependent.",
        "",
        "## Cell-level summary",
        "",
        f"- Median per-cell Pearson correlation: {_fmt(overall['median_cell_pearson_r'])}",
        f"- Median per-cell MAE: {_fmt(overall['median_cell_mae_mm'])} mm/month",
        f"- Median per-cell RMSE: {_fmt(overall['median_cell_rmse_mm'])} mm/month",
        f"- Cells meeting the configured coverage threshold: {overall['cells_meeting_coverage_threshold']} of {overall['n_reference_cells']}",
        "",
        "## Interpretation and limitations",
        "",
        "- This is a cross-product consistency assessment, not independent station validation.",
        "- IMERG Final includes monthly GPCC gauge adjustment.",
        "- POWER PRECTOTCORR uses observation-corrected MERRA-2 precipitation forcing. Over continental Africa, that forcing uses the CMAP gauge-satellite product.",
        "- The two products therefore have different processing chains but both incorporate gauge-informed precipitation information.",
        "- IMERG was aggregated over approximate POWER cell rectangles inferred from cell-centre spacing. Those are not official NASA POWER cell polygons.",
        "- Missing observations were not interpolated. Metrics use paired valid months only.",
        "- IMERG quality and gauge-weighting layers are retained as diagnostics, not used as arbitrary filtering thresholds.",
        "",
        "## Data products",
        "",
        f"- POWER: {metadata['power_product']}",
        f"- IMERG: {metadata['imerg_product']} ({metadata['imerg_collection_id']})",
        f"- IMERG DOI: {metadata['imerg_doi']}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
