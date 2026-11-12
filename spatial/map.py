"""Folium rendering for the native NASA POWER regional grid."""
import html

import folium
import numpy as np
import pandas as pd
from branca.colormap import LinearColormap
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union

from earthscope.spatial.analysis import (
    cell_trend_table,
    filter_cells_to_boundary,
    grid_cell_bounds,
    period_cell_means,
)

EVIDENCE_COLORS = {
    "significant_after_fdr_increasing": "#238B57",
    "significant_after_fdr_decreasing": "#C84C4C",
    "significant_before_fdr_only": "#D99B32",
    "not_significant": "#89939A",
    "insufficient_data": "#C7CDCF",
}


def _trend_colour(row):
    evidence = row.get("evidence_class", "insufficient_data")
    direction = row.get("trend", "no trend")
    if evidence == "significant_after_fdr":
        return EVIDENCE_COLORS[
            "significant_after_fdr_increasing" if direction == "increasing"
            else "significant_after_fdr_decreasing"
        ]
    return EVIDENCE_COLORS.get(evidence, EVIDENCE_COLORS["insufficient_data"])


def _country_geometry(boundary_geojson):
    if not boundary_geojson:
        return None
    geometries = [
        shape(feature["geometry"])
        for feature in boundary_geojson.get("features", [])
        if feature.get("geometry")
    ]
    return unary_union(geometries) if geometries else None


def _add_grid_cell(fmap, row, colour, tooltip, lat_step, lon_step, country_geometry=None):
    """Add an approximate cell footprint, clipped to the Ghana boundary when available."""
    cell_geometry = box(
        row.longitude - lon_step / 2,
        row.latitude - lat_step / 2,
        row.longitude + lon_step / 2,
        row.latitude + lat_step / 2,
    )
    if country_geometry is not None:
        cell_geometry = cell_geometry.intersection(country_geometry)
    if cell_geometry.is_empty:
        return
    folium.GeoJson(
        mapping(cell_geometry),
        style_function=lambda feature, fill=colour: {
            "color": fill, "weight": 0.55, "fillColor": fill, "fillOpacity": 0.78,
        },
        tooltip=folium.Tooltip(tooltip, sticky=True),
    ).add_to(fmap)


def build_regional_grid_map(frame, variable, start_year, end_year, mode="Mean value",
                            boundary_geojson=None, focus_coordinates=None,
                            selected_location=None, study_points=None):
    """Render clipped native-grid footprints with a legend and per-cell tooltips.

    Footprints are approximations derived from returned cell-centre spacing.
    They are not official NASA cell-boundary polygons. If administrative
    boundaries are supplied, cells are retained only when their centres fall
    within the Ghana boundary union and their display footprints are clipped
    to that union.
    """
    if frame.empty:
        raise ValueError("No regional grid data are available for this selection")
    # Infer the native grid spacing from all returned centres before filtering;
    # a coastal/national subset may contain only one centre along one axis.
    lat_step, lon_step = grid_cell_bounds(frame)
    country_geometry = _country_geometry(boundary_geojson)
    display_frame = (
        filter_cells_to_boundary(frame, boundary_geojson)
        if country_geometry is not None else frame.copy()
    )
    if display_frame.empty:
        raise ValueError("No returned NASA POWER cell centres fall within the Ghana boundary")
    if focus_coordinates is not None:
        map_center = [float(focus_coordinates[0]), float(focus_coordinates[1])]
        map_zoom = 8
    else:
        map_center = [7.95, -1.05]
        map_zoom = 6
    fmap = folium.Map(
        location=map_center, zoom_start=map_zoom, tiles="OpenStreetMap",
        control_scale=True, prefer_canvas=True,
    )

    if mode == "Mean value":
        summary = period_cell_means(display_frame, start_year, end_year)
        summary = summary[summary["mean_value"].notna()].copy()
        if summary.empty:
            raise ValueError("No valid values are available in the selected period")
        vmin, vmax = float(summary["mean_value"].min()), float(summary["mean_value"].max())
        if np.isclose(vmin, vmax):
            vmax = vmin + max(abs(vmin) * 0.01, 0.01)
        cmap = LinearColormap(
            ["#440154", "#31688E", "#35B779", "#FDE725"],
            vmin=vmin, vmax=vmax,
        )
        unit = summary["unit"].dropna().iloc[0] if summary["unit"].notna().any() else ""
        cmap.caption = f"{variable} period mean ({unit})"
        cmap.add_to(fmap)
        for row in summary.itertuples(index=False):
            colour = cmap(float(row.mean_value))
            tooltip = (
                f"<b>{html.escape(str(row.cell_id))}</b><br>"
                f"Mean: {row.mean_value:.3f} {html.escape(str(row.unit or ''))}<br>"
                f"Valid months: {int(row.n_months)}<br>"
                f"Cell centre: {row.latitude:.3f}, {row.longitude:.3f}"
            )
            _add_grid_cell(
                fmap, row, colour, tooltip, lat_step, lon_step, country_geometry
            )
    elif mode == "Trend evidence":
        summary = cell_trend_table(display_frame, variable)
        if summary.empty:
            raise ValueError("No cell-level trend results could be calculated")
        for row in summary.itertuples(index=False):
            colour = _trend_colour(row._asdict())
            slope = "Not available" if pd.isna(row.sen_per_decade) else f"{row.sen_per_decade:.4f} {row.unit}/decade"
            p_fdr = "Not available" if pd.isna(row.mk_p_fdr) else f"{row.mk_p_fdr:.4g}"
            p_raw = "Not available" if pd.isna(row.mk_p) else f"{row.mk_p:.4g}"
            tooltip = (
                f"<b>{html.escape(str(row.cell_id))}</b><br>"
                f"Trend: {html.escape(str(row.trend))}<br>"
                f"Sen's slope: {html.escape(slope)}<br>"
                f"FDR-adjusted p: {p_fdr}<br>Raw p: {p_raw}<br>"
                f"Valid years: {int(row.n_years)}<br>"
                f"Cell centre: {row.latitude:.3f}, {row.longitude:.3f}"
            )
            _add_grid_cell(
                fmap, row, colour, tooltip, lat_step, lon_step, country_geometry
            )

        legend = """
        <div style="position:fixed;bottom:28px;left:18px;z-index:9999;background:#fff;
                    padding:10px 12px;border:1px solid #9aa9a5;border-radius:7px;
                    box-shadow:0 1px 5px rgba(0,0,0,.18);font-size:12px;color:#203744">
          <b>Trend evidence</b><br>
          <span style="color:#238B57">■</span> Increasing, significant after FDR<br>
          <span style="color:#C84C4C">■</span> Decreasing, significant after FDR<br>
          <span style="color:#D99B32">■</span> Raw p &lt; 0.05 only<br>
          <span style="color:#89939A">■</span> Not significant<br>
          <span style="color:#C7CDCF">■</span> Insufficient data
        </div>
        """
        fmap.get_root().html.add_child(folium.Element(legend))
    else:
        raise ValueError("mode must be 'Mean value' or 'Trend evidence'")

    if boundary_geojson:
        selected_geometry = None
        if focus_coordinates is not None:
            focus_point = Point(float(focus_coordinates[1]), float(focus_coordinates[0]))
            for feature in boundary_geojson.get("features", []):
                if feature.get("geometry") and shape(feature["geometry"]).covers(focus_point):
                    selected_geometry = feature["geometry"]
                    break

        def boundary_style(feature):
            is_selected = (
                selected_geometry is not None
                and feature.get("geometry") == selected_geometry
            )
            return {
                "color": "#D97736" if is_selected else "#526875",
                "weight": 2.8 if is_selected else 0.45,
                "fillColor": "#D97736" if is_selected else "#FFFFFF",
                "fillOpacity": 0.10 if is_selected else 0,
            }

        folium.GeoJson(
            boundary_geojson,
            name="Ghana district boundaries",
            style_function=boundary_style,
            overlay=True,
            control=True,
        ).add_to(fmap)

    # Keep the selected NASA POWER location in the map as a reference only.
    # The coloured grid cells remain the spatial data layer, not a marker surface.
    if focus_coordinates is not None and selected_location:
        folium.CircleMarker(
            location=map_center,
            radius=4,
            color="#203744",
            weight=1.2,
            fill=True,
            fill_color="#FFFFFF",
            fill_opacity=1,
            tooltip=f"{selected_location} reference grid-cell centre",
        ).add_to(fmap)

    if focus_coordinates is None:
        fmap.fit_bounds([[4.5, -3.5], [11.4, 1.5]])
    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap, summary, (lat_step, lon_step)
