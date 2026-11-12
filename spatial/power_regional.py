"""NASA POWER regional monthly grid retrieval for Ghana.

Regional responses are retained on each parameter's native grid. No spatial
interpolation or resampling is performed. NASA's regional monthly service accepts
one parameter per request, so each variable is fetched separately for each tile.
"""
from __future__ import annotations

import json
import math
import time
from typing import Iterable

import numpy as np
import pandas as pd
import requests

from earthscope import config

API_URL = "https://power.larc.nasa.gov/api/temporal/monthly/regional"
MAX_TILE_SPAN_DEGREES = 4.0  # conservative, below the commonly documented 4.5-degree regional limit
FILL_VALUE = -999.0
COLUMNS = [
    "date", "variable", "value", "latitude", "longitude", "cell_id",
    "unit", "unit_source", "source", "data_kind", "tile_id",
]


class RegionalPowerError(RuntimeError):
    """A NASA POWER regional request or response could not be used safely."""


def build_tiles(bbox=None, max_span=MAX_TILE_SPAN_DEGREES):
    """Split (west, south, east, north) into non-overlapping request boxes."""
    west, south, east, north = bbox or config.GHANA_BBOX
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be (west, south, east, north) in valid geographic coordinates")
    if not (0 < max_span <= 4.5):
        raise ValueError("max_span must be greater than 0 and no more than 4.5 degrees")
    tiles = []
    lat0 = south
    while lat0 < north - 1e-9:
        lat1 = min(lat0 + max_span, north)
        lon0 = west
        while lon0 < east - 1e-9:
            lon1 = min(lon0 + max_span, east)
            tiles.append({
                "west": round(lon0, 6), "south": round(lat0, 6),
                "east": round(lon1, 6), "north": round(lat1, 6),
            })
            lon0 = lon1
        lat0 = lat1
    return tiles


def build_request_params(variable, tile, start_year, end_year, community=None):
    """Build query parameters for one variable and one bounded regional tile."""
    if variable not in config.POWER_PARAMS:
        raise ValueError(f"Unsupported NASA POWER variable: {variable}")
    if int(start_year) > int(end_year):
        raise ValueError("start_year must be less than or equal to end_year")
    return {
        "parameters": variable,
        "community": community or config.POWER_COMMUNITY,
        "latitude-min": tile["south"],
        "latitude-max": tile["north"],
        "longitude-min": tile["west"],
        "longitude-max": tile["east"],
        "start": int(start_year),
        "end": int(end_year),
        "format": "JSON",
    }


def _unit_from_metadata(payload, variable):
    """Return a unit only when the NASA response explicitly supplies one."""
    candidates = []
    if isinstance(payload, dict):
        for key in ("parameters", "parameter_metadata", "metadata"):
            block = payload.get(key)
            if isinstance(block, dict) and isinstance(block.get(variable), dict):
                candidates.append(block[variable])
        for feature in payload.get("features", []) or []:
            props = feature.get("properties", {}) or {}
            for key in ("parameters", "parameter_metadata", "metadata"):
                block = props.get(key)
                if isinstance(block, dict) and isinstance(block.get(variable), dict):
                    candidates.append(block[variable])
    for item in candidates:
        unit = item.get("units") or item.get("unit")
        if unit:
            return str(unit)
    return None


def parse_regional_payload(payload, variable, tile_id="tile-0"):
    """Parse a NASA POWER regional GeoJSON response into one row per cell and month.

    Only Point geometries and explicit YYYYMM monthly values are accepted. Annual
    summary keys (YYYY13) are excluded. Missing/fill values remain NaN.
    """
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise RegionalPowerError("Regional response is not a GeoJSON FeatureCollection")
    features = payload.get("features") or []
    if not features:
        raise RegionalPowerError("Regional response contains no grid-cell features")

    fill = FILL_VALUE
    header = payload.get("header") or {}
    try:
        fill = float(header.get("fill_value", FILL_VALUE))
    except (TypeError, ValueError):
        pass
    unit = _unit_from_metadata(payload, variable)
    expected_unit = config.EXPECTED_UNITS.get(variable)
    unit_source = "response_metadata" if unit else "not_stated_in_regional_response"

    rows = []
    for feature_index, feature in enumerate(features):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point":
            raise RegionalPowerError(
                f"Feature {feature_index} is not a Point geometry; refusing to infer cell coordinates"
            )
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            raise RegionalPowerError(f"Feature {feature_index} has invalid coordinates")
        lon, lat = float(coords[0]), float(coords[1])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise RegionalPowerError(f"Feature {feature_index} has out-of-range coordinates")

        props = feature.get("properties") or {}
        param_block = props.get("parameter") or props.get("parameters") or {}
        series = param_block.get(variable) if isinstance(param_block, dict) else None
        if not isinstance(series, dict):
            raise RegionalPowerError(
                f"Feature {feature_index} does not contain a monthly series for {variable}"
            )
        cell_id = f"{lat:.4f}_{lon:.4f}"
        for date_key, raw_value in series.items():
            key = str(date_key)
            if len(key) != 6 or not key.isdigit():
                continue
            year, month = int(key[:4]), int(key[4:])
            if month == 13:  # POWER annual summary, not a monthly observation
                continue
            if not 1 <= month <= 12:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                value = np.nan
            if raw_value is None or not math.isfinite(value) or value == fill:
                value = np.nan
            rows.append({
                "date": pd.Timestamp(year=year, month=month, day=1),
                "variable": variable, "value": value,
                "latitude": lat, "longitude": lon, "cell_id": cell_id,
                "unit": unit or expected_unit, "unit_source": unit_source,
                "source": "NASA POWER regional monthly",
                "data_kind": "gridded_estimate_not_station_observation",
                "tile_id": tile_id,
            })

    if not rows:
        raise RegionalPowerError(f"No monthly values for {variable} were found in regional response")
    result = pd.DataFrame(rows, columns=COLUMNS)
    return result.drop_duplicates(["date", "variable", "cell_id"]).sort_values(
        ["cell_id", "date"]
    ).reset_index(drop=True)


def fetch_tile(variable, tile, start_year, end_year, session=None, timeout=(20, 180), retries=3):
    """Fetch one variable/tile from the official NASA POWER regional monthly endpoint."""
    client = session or requests
    params = build_request_params(variable, tile, start_year, end_year)
    last_error = None
    for attempt in range(retries):
        try:
            response = client.get(API_URL, params=params, timeout=timeout)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise RegionalPowerError("NASA POWER returned a non-JSON regional response") from exc
            tile_id = (
                f"{tile['west']}_{tile['south']}_{tile['east']}_{tile['north']}"
            )
            parsed = parse_regional_payload(payload, variable, tile_id=tile_id)
            return parsed, {
                "request_url": getattr(response, "url", API_URL),
                "http_status": int(response.status_code),
                "tile": tile,
                "variable": variable,
                "start_year": int(start_year),
                "end_year": int(end_year),
                "feature_count": len(payload.get("features", [])),
                "response_unit": _unit_from_metadata(payload, variable),
            }
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status is not None and 400 <= status < 500:
                raise RegionalPowerError(f"NASA POWER rejected {variable} tile: {exc}") from exc
            last_error = exc
        except (requests.RequestException, ValueError, RegionalPowerError) as exc:
            last_error = exc
            if isinstance(exc, RegionalPowerError) and "non-JSON" not in str(exc):
                raise
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise RegionalPowerError(f"NASA POWER request failed after {retries} attempts: {last_error}")


def fetch_parameter(variable, start_year=None, end_year=None, bbox=None, session=None):
    """Fetch a complete Ghana regional monthly series for one variable.

    The solar series starts in 1984. Meteorological parameters start in 1981.
    Each parameter retains its own native grid; overlapping tile edge cells are
    deduplicated by their returned coordinates.
    """
    start_year = int(start_year or (1984 if variable == "ALLSKY_SFC_SW_DWN" else config.POWER_START_YEAR))
    end_year = int(end_year or config.latest_complete_year())
    if variable == "ALLSKY_SFC_SW_DWN":
        start_year = max(start_year, 1984)
    tiles = build_tiles(bbox=bbox)
    frames, records = [], []
    for i, tile in enumerate(tiles, start=1):
        frame, record = fetch_tile(
            variable, tile, start_year, end_year, session=session
        )
        frames.append(frame)
        record["tile_number"] = i
        records.append(record)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        ["date", "variable", "latitude", "longitude"]
    ).sort_values(["latitude", "longitude", "date"]).reset_index(drop=True)
    combined.attrs["fetch_records"] = records
    combined.attrs["requested_period"] = {"start_year": start_year, "end_year": end_year}
    combined.attrs["bbox"] = bbox or config.GHANA_BBOX
    return combined


def estimate_grid_spacing(frame):
    """Describe observed coordinate spacing without resampling or claiming a fixed resolution."""
    if frame.empty:
        return {"latitude_spacing_degrees": None, "longitude_spacing_degrees": None}
    lat = np.sort(frame["latitude"].dropna().unique())
    lon = np.sort(frame["longitude"].dropna().unique())
    def median_positive_spacing(values):
        diffs = np.diff(values)
        diffs = diffs[diffs > 1e-6]
        return float(np.median(diffs)) if len(diffs) else None
    return {
        "latitude_spacing_degrees": median_positive_spacing(lat),
        "longitude_spacing_degrees": median_positive_spacing(lon),
        "interpretation": "Estimated from returned cell-centre coordinates; not a resampled grid resolution.",
    }


def available_years(frame):
    """Return years with at least one non-missing regional value."""
    if frame.empty:
        return []
    valid = frame.loc[frame["value"].notna(), "date"]
    return sorted(valid.dt.year.unique().astype(int).tolist())
