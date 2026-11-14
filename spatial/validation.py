"""Pre-analysis quality checks for NASA POWER regional monthly grids.

The validator is intentionally non-destructive: it never fills, clips, averages,
or removes observations. It reports defects and marks whether a frame is eligible
for downstream trend analysis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from earthscope import config

REQUIRED_COLUMNS = {
    "date", "variable", "value", "latitude", "longitude", "cell_id",
    "unit", "unit_source", "source", "data_kind",
}

# Broad physical plausibility bounds for screening, not scientific thresholds.
PHYSICAL_BOUNDS = {
    "T2M": (-90.0, 65.0),
    "T2M_MAX": (-90.0, 70.0),
    "T2M_MIN": (-100.0, 60.0),
    "PRECTOTCORR": (0.0, 150.0),
    "RH2M": (0.0, 100.0),
    "WS10M": (0.0, 100.0),
    "ALLSKY_SFC_SW_DWN": (0.0, 50.0),
}


def validate_regional_frame(
    frame: pd.DataFrame,
    variable: str,
    start_year: int,
    end_year: int,
    minimum_cell_coverage: float = 0.80,
) -> dict:
    """Return a reproducible QC summary without changing the supplied frame.

    Fatal structural defects make the frame ineligible. Physically implausible
    values also block analysis until reviewed. Missing observations are retained
    and reported per cell; they are never interpolated.
    """
    if not 0 < minimum_cell_coverage <= 1:
        raise ValueError("minimum_cell_coverage must be in (0, 1]")
    start_year, end_year = int(start_year), int(end_year)
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")

    errors, warnings = [], []
    report = {
        "variable": variable,
        "requested_start_year": start_year,
        "requested_end_year": end_year,
        "rows": int(len(frame)),
        "cells": 0,
        "expected_months_per_cell": (end_year - start_year + 1) * 12,
        "valid_observations": 0,
        "missing_observations": 0,
        "overall_valid_fraction": None,
        "minimum_cell_coverage_threshold": float(minimum_cell_coverage),
        "minimum_cell_valid_fraction": None,
        "median_cell_valid_fraction": None,
        "first_valid_month": None,
        "last_valid_month": None,
        "units": [],
        "unit_sources": [],
        "out_of_range_observations": 0,
        "duplicate_cell_month_records": 0,
        "errors": errors,
        "warnings": warnings,
    }

    missing_columns = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing_columns:
        errors.append("Missing required columns: " + ", ".join(missing_columns))
        report.update(status="fail", analysis_eligible=False)
        return report
    if frame.empty:
        errors.append("The regional dataset is empty.")
        report.update(status="fail", analysis_eligible=False)
        return report

    d = frame.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["latitude"] = pd.to_numeric(d["latitude"], errors="coerce")
    d["longitude"] = pd.to_numeric(d["longitude"], errors="coerce")
    d["value"] = pd.to_numeric(d["value"], errors="coerce")

    if d["variable"].dropna().nunique() != 1 or d["variable"].dropna().iloc[0] != variable:
        errors.append(f"Expected only {variable} records.")
    if d["date"].isna().any():
        errors.append(f"{int(d['date'].isna().sum())} rows have invalid dates.")
    else:
        if not d["date"].dt.day.eq(1).all():
            errors.append("Dates must be month-start timestamps.")
        outside = ~d["date"].dt.year.between(start_year, end_year)
        if outside.any():
            errors.append(f"{int(outside.sum())} rows fall outside the requested year range.")

    bad_coords = (
        ~np.isfinite(d["latitude"]) | ~np.isfinite(d["longitude"])
        | ~d["latitude"].between(-90, 90) | ~d["longitude"].between(-180, 180)
    )
    if bad_coords.any():
        errors.append(f"{int(bad_coords.sum())} rows have invalid coordinates.")

    duplicate_mask = d.duplicated(["cell_id", "date"], keep=False)
    report["duplicate_cell_month_records"] = int(duplicate_mask.sum())
    if duplicate_mask.any():
        errors.append(f"{int(duplicate_mask.sum())} rows belong to duplicated cell-month keys.")

    coord_counts = d.groupby("cell_id", dropna=False)[["latitude", "longitude"]].nunique(dropna=False)
    if (coord_counts > 1).any(axis=None):
        errors.append("At least one cell_id maps to more than one coordinate pair.")

    expected_ids = (
        d["latitude"].round(4).astype("string") + "_" +
        d["longitude"].round(4).astype("string")
    )
    if not d["cell_id"].astype("string").equals(expected_ids):
        warnings.append("Some cell_id values do not match the parser's rounded coordinate convention.")

    report["cells"] = int(d["cell_id"].nunique(dropna=True))
    report["units"] = sorted(d["unit"].dropna().astype(str).unique().tolist())
    report["unit_sources"] = sorted(d["unit_source"].dropna().astype(str).unique().tolist())
    expected_unit = config.EXPECTED_UNITS.get(variable)
    if len(report["units"]) > 1:
        errors.append("Mixed units found in one variable dataset.")
    elif report["units"] and expected_unit and report["units"][0] != expected_unit:
        errors.append(f"Unit mismatch: expected {expected_unit}, found {report['units'][0]}.")
    if not report["units"]:
        errors.append("No unit is recorded.")
    if "response_metadata" not in report["unit_sources"]:
        warnings.append("The regional response did not explicitly provide unit metadata; configured units may be fallback labels.")

    if d["value"].notna().any():
        report["first_valid_month"] = d.loc[d["value"].notna(), "date"].min().strftime("%Y-%m")
        report["last_valid_month"] = d.loc[d["value"].notna(), "date"].max().strftime("%Y-%m")
    report["valid_observations"] = int(d["value"].notna().sum())
    report["missing_observations"] = int(d["value"].isna().sum())
    total_expected = report["cells"] * report["expected_months_per_cell"]
    report["overall_valid_fraction"] = (
        report["valid_observations"] / total_expected if total_expected else None
    )

    coverage = d.assign(valid=d["value"].notna()).groupby("cell_id")["valid"].sum()
    cell_fraction = coverage / report["expected_months_per_cell"]
    if len(cell_fraction):
        report["minimum_cell_valid_fraction"] = float(cell_fraction.min())
        report["median_cell_valid_fraction"] = float(cell_fraction.median())
        below = int((cell_fraction < minimum_cell_coverage).sum())
        if below:
            warnings.append(
                f"{below} of {len(cell_fraction)} cells fall below "
                f"{minimum_cell_coverage:.0%} valid-month coverage."
            )

    bounds = PHYSICAL_BOUNDS.get(variable)
    if bounds:
        out_of_range = d["value"].notna() & ~d["value"].between(*bounds)
        report["out_of_range_observations"] = int(out_of_range.sum())
        if out_of_range.any():
            errors.append(
                f"{int(out_of_range.sum())} values fall outside the broad screening range "
                f"{bounds[0]} to {bounds[1]} {expected_unit or ''}."
            )

    if report["valid_observations"] == 0:
        errors.append("No valid numeric observations were found.")

    report["status"] = "fail" if errors else ("warn" if warnings else "pass")
    report["analysis_eligible"] = not errors
    return report
