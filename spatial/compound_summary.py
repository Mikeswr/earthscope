"""Derived summaries for the retrospective compound hot-dry analysis.

These summaries aggregate grid-cell-centre results without interpolation.
National annual means are explicitly unweighted grid-cell means, not area-
weighted national estimates.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from earthscope.trends import engine


ANNUAL_REQUIRED = {
    "year", "cell_id", "latitude", "longitude",
    "n_months_assessed", "n_hot_dry_months", "hot_dry_frequency_pct",
}
TREND_FIELDS = [
    "sen_frequency_change_pp_per_decade",
    "sen_ci_low_pp_per_decade",
    "sen_ci_high_pp_per_decade",
    "mk_p",
    "mk_p_fdr_by",
    "mk_p_fdr_bh",
    "evidence_class_by",
    "evidence_class_bh_sensitivity",
]


def summarise_compound_outputs(annual: pd.DataFrame, trends: pd.DataFrame):
    """Return annual grid summaries, cell summaries and a centroid GeoJSON.

    Every annual value remains tied to its original cell and year. No spatial
    interpolation or area weighting is performed.
    """
    missing = ANNUAL_REQUIRED - set(annual.columns)
    if missing:
        raise ValueError("Annual compound table missing columns: " + ", ".join(sorted(missing)))
    if annual.empty:
        raise ValueError("Annual compound table is empty.")
    if annual.duplicated(["cell_id", "year"]).any():
        raise ValueError("Duplicate cell-year records found in annual compound table.")

    a = annual.copy()
    for col in ["year", "latitude", "longitude", "n_months_assessed",
                "n_hot_dry_months", "hot_dry_frequency_pct"]:
        a[col] = pd.to_numeric(a[col], errors="coerce")
    if a[["year", "latitude", "longitude"]].isna().any(axis=None):
        raise ValueError("Annual compound table contains invalid year or coordinate values.")
    if a["cell_id"].isna().any():
        raise ValueError("Annual compound table contains missing cell IDs.")
    if (a["n_hot_dry_months"].dropna() < 0).any():
        raise ValueError("Annual compound table contains negative event counts.")
    if (
        a["n_months_assessed"].notna()
        & a["n_hot_dry_months"].notna()
        & (a["n_hot_dry_months"] > a["n_months_assessed"])
    ).any():
        raise ValueError("Compound event counts cannot exceed assessed months.")
    if not a["hot_dry_frequency_pct"].dropna().between(0, 100).all():
        raise ValueError("Annual compound frequencies must be within 0 to 100 percent.")
    coordinate_counts = a.groupby("cell_id")[["latitude", "longitude"]].nunique()
    if (coordinate_counts > 1).any(axis=None):
        raise ValueError("Cell IDs must map to stable coordinates across years.")

    a["_assessed_event_months"] = a["n_hot_dry_months"].where(
        a["hot_dry_frequency_pct"].notna()
    )
    a["_has_event_when_assessed"] = (
        a["n_hot_dry_months"].gt(0) & a["hot_dry_frequency_pct"].notna()
    )

    annual_summary = (
        a.groupby("year", as_index=False)
        .agg(
            n_grid_cells_assessed=("hot_dry_frequency_pct", "count"),
            total_compound_hot_dry_cell_months=("_assessed_event_months", "sum"),
            mean_cell_annual_frequency_pct=("hot_dry_frequency_pct", "mean"),
            median_cell_annual_frequency_pct=("hot_dry_frequency_pct", "median"),
            n_cells_with_at_least_one_event=(
                "_has_event_when_assessed", "sum"
            ),
            n_cell_years_assessed=("hot_dry_frequency_pct", "count"),
        )
    )
    annual_summary["pct_cells_with_at_least_one_event"] = (
        100 * annual_summary["n_cells_with_at_least_one_event"]
        / annual_summary["n_grid_cells_assessed"]
    )

    cell_summary = (
        a.groupby(["cell_id", "latitude", "longitude"], as_index=False)
        .agg(
            n_years_assessed=("hot_dry_frequency_pct", "count"),
            total_compound_hot_dry_months=("_assessed_event_months", "sum"),
            n_years_with_at_least_one_event=(
                "_has_event_when_assessed", "sum"
            ),
            mean_annual_frequency_pct=("hot_dry_frequency_pct", "mean"),
            median_annual_frequency_pct=("hot_dry_frequency_pct", "median"),
            maximum_annual_frequency_pct=("hot_dry_frequency_pct", "max"),
        )
    )
    cell_summary["pct_assessed_years_with_no_event"] = (
        100 * (cell_summary["n_years_assessed"] - cell_summary["n_years_with_at_least_one_event"])
        / cell_summary["n_years_assessed"]
    )
    cell_summary["pct_assessed_years_with_event"] = (
        100 * cell_summary["n_years_with_at_least_one_event"]
        / cell_summary["n_years_assessed"]
    )

    if not trends.empty:
        trend_missing = {"cell_id"} - set(trends.columns)
        if trend_missing:
            raise ValueError("Trend table is missing cell_id.")
        keep = ["cell_id"] + [c for c in TREND_FIELDS if c in trends.columns]
        if trends["cell_id"].duplicated().any():
            raise ValueError("Duplicate cell IDs found in trend table.")
        cell_summary = cell_summary.merge(
            trends[keep], on="cell_id", how="left", validate="one_to_one"
        )

    features = []
    for row in cell_summary.to_dict(orient="records"):
        properties = {}
        for key, value in row.items():
            if key in ("latitude", "longitude"):
                continue
            if pd.isna(value):
                properties[key] = None
            elif isinstance(value, (np.integer,)):
                properties[key] = int(value)
            elif isinstance(value, (np.floating, float)):
                properties[key] = float(value)
            else:
                properties[key] = value
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["longitude"]), float(row["latitude"])],
            },
            "properties": properties,
        })
    geojson = {
        "type": "FeatureCollection",
        "name": "earthscope_compound_hot_dry_grid_cell_centres",
        "metadata": {
            "geometry_semantics": "Returned NASA POWER grid-cell centroids; not station locations or cell polygons.",
            "spatial_interpolation": False,
            "cell_summary_weighting": "Unweighted across retained grid-cell centres.",
        },
        "features": features,
    }
    domain_series = annual_summary.set_index("year")["mean_cell_annual_frequency_pct"]
    domain_mk = engine.mann_kendall(
        domain_series, alpha=0.05, autocorrelation="ar1_neff"
    )
    domain_trend = {
        "series": "Unweighted mean annual compound hot-dry frequency across retained grid-cell centres",
        "n_valid_years": int(domain_mk["n"]),
        "year_span": int(domain_mk["n_span"]),
        "trend_direction": domain_mk["trend"],
        "sen_slope_percentage_points_per_decade": engine.sens_slope_per_decade(domain_series),
        "sen_ci_low_percentage_points_per_decade": (
            float(domain_mk["slope_ci_low"] * 10)
            if np.isfinite(domain_mk["slope_ci_low"]) else None
        ),
        "sen_ci_high_percentage_points_per_decade": (
            float(domain_mk["slope_ci_high"] * 10)
            if np.isfinite(domain_mk["slope_ci_high"]) else None
        ),
        "mann_kendall_p": (
            float(domain_mk["p"]) if np.isfinite(domain_mk["p"]) else None
        ),
        "kendall_tau": (
            float(domain_mk["tau"]) if np.isfinite(domain_mk["tau"]) else None
        ),
        "lag1_autocorrelation": (
            float(domain_mk["rho1"]) if np.isfinite(domain_mk["rho1"]) else None
        ),
        "variance_factor": (
            float(domain_mk["variance_factor"])
            if np.isfinite(domain_mk["variance_factor"]) else None
        ),
        "autocorrelation_method": "AR(1) effective-sample-size variance adjustment",
        "status": "exploratory aggregate time-series test; not a spatially area-weighted national estimate",
    }
    summary_metadata = {
        "n_grid_cells": int(cell_summary["cell_id"].nunique()),
        "n_annual_grid_summaries": int(len(annual_summary)),
        "n_cell_years_assessed": int(annual_summary["n_cell_years_assessed"].sum()),
        "total_classified_compound_hot_dry_cell_months": int(
            annual_summary["total_compound_hot_dry_cell_months"].sum()
        ),
        "domain_aggregate_trend": domain_trend,
        "spatial_inference": (
            "Summaries describe retained NASA POWER grid-cell centres inside the supplied "
            "Ghana boundary. Annual cell summaries are unweighted and are not an area-weighted "
            "national estimate."
        ),
    }
    return (
        annual_summary.sort_values("year").reset_index(drop=True),
        cell_summary.sort_values(["latitude", "longitude"]).reset_index(drop=True),
        geojson,
        summary_metadata,
    )


def write_compound_summaries(annual, trends, output_dir):
    """Write annual and cell-level derivative tables and a centroid GeoJSON."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    annual_summary, cell_summary, geojson, metadata = summarise_compound_outputs(
        annual, trends
    )
    annual_path = out / "compound_hot_dry_annual_summary.csv"
    cell_path = out / "compound_hot_dry_cell_summary.csv"
    geo_path = out / "compound_hot_dry_cell_centres.geojson"
    annual_summary.to_csv(annual_path, index=False)
    cell_summary.to_csv(cell_path, index=False)
    geo_path.write_text(json.dumps(geojson, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {
        "annual_summary": {"file": annual_path.name, "rows": len(annual_summary)},
        "cell_summary": {"file": cell_path.name, "rows": len(cell_summary)},
        "cell_centres_geojson": {"file": geo_path.name, "features": len(geojson["features"])},
        "summary_metadata": metadata,
    }
