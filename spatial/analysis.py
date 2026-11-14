"""Per-cell spatial summaries and statistically corrected trend evidence."""
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from earthscope import config
from earthscope.trends import engine
from earthscope.trends.pipeline import annual_series


def period_cell_means(frame, start_year, end_year):
    """Return each native grid cell's mean over a selected inclusive year range."""
    if frame.empty:
        return pd.DataFrame(columns=["cell_id", "latitude", "longitude", "mean_value", "n_months", "unit"])
    selected = frame[
        frame["date"].dt.year.between(int(start_year), int(end_year))
    ].copy()
    if selected.empty:
        return pd.DataFrame(columns=["cell_id", "latitude", "longitude", "mean_value", "n_months", "unit"])
    return (
        selected.groupby("cell_id", as_index=False)
        .agg(
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            mean_value=("value", "mean"),
            n_months=("value", "count"),
            unit=("unit", "first"),
        )
    )


def cell_trend_table(frame, variable, alpha=0.05, fdr_method="bh"):
    """Calculate annual MK and Sen trends for each returned grid cell.

    Every cell is tested on its own complete monthly calendar. Annual means use
    the same parameter-specific aggregation and 12-month completeness rule as
    the existing EarthScope point analysis. FDR is applied across valid cells
    for this variable. No spatial interpolation is performed.
    """
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for cell_id, group in frame[frame["variable"] == variable].groupby("cell_id"):
        group = group.sort_values("date")
        values = group.set_index("date")["value"]
        if values.index.has_duplicates:
            duplicate_dates = values.index[values.index.duplicated()].unique()
            preview = ", ".join(pd.Timestamp(x).strftime("%Y-%m") for x in duplicate_dates[:5])
            raise ValueError(
                f"Duplicate cell-month records for {cell_id} ({preview}). "
                "Resolve the ingestion issue before trend analysis; records are never averaged silently."
            )
        if values.empty:
            continue
        monthly = values.reindex(
            pd.date_range(values.index.min(), values.index.max(), freq="MS")
        )
        annual = annual_series(
            monthly,
            min_months=12,
            how=config.annual_how(variable),
        )
        result = engine.mann_kendall(annual, alpha=alpha, autocorrelation="ar1_neff")
        rows.append({
            "cell_id": cell_id,
            "latitude": float(group["latitude"].iloc[0]),
            "longitude": float(group["longitude"].iloc[0]),
            "unit": group["unit"].dropna().iloc[0] if group["unit"].notna().any() else config.EXPECTED_UNITS.get(variable),
            "n_years": int(result["n"]),
            "year_span": int(result["n_span"]),
            "trend": result["trend"],
            "sen_per_decade": engine.sens_slope_per_decade(annual),
            "mk_p": result["p"],
            "mk_reason": result["reason"],
        })
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["mk_p_fdr"] = engine.fdr_adjust(table["mk_p"].to_numpy(), alpha=alpha, method=fdr_method)
    table["evidence_class"] = np.select(
        [
            table["trend"].eq("insufficient_data"),
            table["mk_p_fdr"].lt(alpha),
            table["mk_p"].lt(alpha),
        ],
        [
            "insufficient_data",
            "significant_after_fdr",
            "significant_before_fdr_only",
        ],
        default="not_significant",
    )
    return table.sort_values(["latitude", "longitude"]).reset_index(drop=True)


def grid_cell_bounds(frame):
    """Infer display footprints from returned cell centres and median coordinate spacing.

    These are approximate map footprints, not official NASA cell-boundary polygons.
    """
    if frame.empty:
        raise ValueError("Cannot infer grid footprints from an empty regional dataset")
    latitudes = np.sort(frame["latitude"].dropna().unique())
    longitudes = np.sort(frame["longitude"].dropna().unique())

    def spacing(values):
        diffs = np.diff(values)
        diffs = diffs[diffs > 1e-6]
        if not len(diffs):
            raise ValueError("At least two unique grid coordinates are required per axis")
        return float(np.median(diffs))

    return spacing(latitudes), spacing(longitudes)



def filter_cells_to_boundary(frame, boundary_geojson):
    """Keep cells whose returned centres fall within the supplied administrative union."""
    if frame.empty or not boundary_geojson:
        return frame.copy()
    geometries = [
        shape(feature["geometry"])
        for feature in boundary_geojson.get("features", [])
        if feature.get("geometry")
    ]
    if not geometries:
        return frame.copy()
    country_geometry = unary_union(geometries)
    centres = frame[["cell_id", "latitude", "longitude"]].drop_duplicates("cell_id")
    inside = {
        row.cell_id
        for row in centres.itertuples(index=False)
        if country_geometry.covers(Point(float(row.longitude), float(row.latitude)))
    }
    return frame[frame["cell_id"].isin(inside)].copy()
