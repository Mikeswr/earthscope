"""Agromonitoring clients (key from AGROMONITORING_API_KEY, see docs/CREDENTIALS.md).

STATUS: written from the Agromonitoring documentation and NOT yet tested against live responses.
VERIFIED_AGAINST_LIVE_API stays False until scripts/check_apis.py has succeeded with your key.

Endpoints (base https://api.agromonitoring.com/agro/1.0):
  weather            GET  /weather?lat&lon                      current weather
  weather/history    GET  /weather/history?lat&lon&start&end    hourly archive; depth depends on plan;
                          temperature is Kelvin unless documented otherwise
  polygons           GET/POST /polygons                         a polygon is required for satellite data
                          (area limit 1 to 3000 ha per the documentation)
  ndvi/history       GET  /ndvi/history?polyid&start&end        NDVI statistics per satellite acquisition
                          (Landsat 8 and Sentinel-2); older archive may need a higher plan
"""
import math

import pandas as pd

from earthscope import config
from earthscope.ingest import http
from earthscope.ingest.power import UnitError

VERIFIED_AGAINST_LIVE_API = False
BASE = "https://api.agromonitoring.com/agro/1.0"
NDVI_COLUMNS = ["polygon_id", "location", "latitude", "longitude", "date", "satellite", "cloud_pct",
                "useful_area_pct", "ndvi_mean", "ndvi_median", "ndvi_p25", "ndvi_p75", "ndvi_min",
                "ndvi_max", "ndvi_std", "n_pixels", "source", "data_kind", "unit"]


def _key():
    return config.get_key(config.ENV_AGROMONITORING)


def current_weather(lat, lon, **kw):
    return http.call("GET", f"{BASE}/weather", secret=_key(), params={"lat": lat, "lon": lon}, **kw)[1]


def weather_history(lat, lon, start_unix, end_unix, **kw):
    return http.call("GET", f"{BASE}/weather/history", secret=_key(),
                     params={"lat": lat, "lon": lon, "start": int(start_unix), "end": int(end_unix)}, **kw)[1]


def list_polygons(**kw):
    return http.call("GET", f"{BASE}/polygons", secret=_key(), **kw)[1]


def create_polygon(name, ring_lon_lat, duplicated=False, **kw):
    """ring_lon_lat: list of [lon, lat] with the first point repeated as the last."""
    if ring_lon_lat[0] != ring_lon_lat[-1]:
        raise ValueError("polygon ring must be closed (first and last position identical)")
    body = {"name": name, "geo_json": {"type": "Feature", "properties": {},
                                       "geometry": {"type": "Polygon", "coordinates": [ring_lon_lat]}}}
    params = {"duplicated": "true"} if duplicated else None
    return http.call("POST", f"{BASE}/polygons", secret=_key(), params=params, json_body=body, **kw)[1]


def square_polygon(lat, lon, half_side_m=250.0):
    """Closed [lon, lat] ring of a square around a point. 250 m half side is about 25 ha."""
    dlat = half_side_m / 111_320.0
    dlon = half_side_m / (111_320.0 * math.cos(math.radians(lat)))
    ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat],
            [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
    return ring


def ndvi_history(polygon_id, start_unix, end_unix, **kw):
    return http.call("GET", f"{BASE}/ndvi/history", secret=_key(),
                     params={"polyid": polygon_id, "start": int(start_unix), "end": int(end_unix)}, **kw)[1]


def parse_weather_history(payload, location, lat, lon):
    """Hourly history -> long table. Kelvin is converted to C explicitly; if the values do not look
    like Kelvin the data is rejected rather than guessed."""
    if not isinstance(payload, list):
        raise ValueError("weather/history response is not a list")
    temps = [e["main"]["temp"] for e in payload if e.get("main", {}).get("temp") is not None]
    if temps and sorted(temps)[len(temps) // 2] < 150:
        raise UnitError("temperature values look like Celsius, but Kelvin was expected; refusing to guess")
    rows = []
    for e in payload:
        ts = pd.to_datetime(e["dt"], unit="s", utc=True).tz_localize(None)
        main, wind, clouds = e.get("main", {}), e.get("wind", {}), e.get("clouds", {})
        items = [("temp", None if main.get("temp") is None else main["temp"] - 273.15, "C",
                  "kelvin_in_response_converted_to_C", "hourly_instantaneous"),
                 ("humidity", main.get("humidity"), "%", "documented", "hourly_instantaneous"),
                 ("pressure", main.get("pressure"), "hPa", "documented", "hourly_instantaneous"),
                 ("wind_speed", wind.get("speed"), "m/s", "documented_default_meter_per_sec", "hourly_instantaneous"),
                 ("cloud_cover", clouds.get("all"), "%", "documented", "hourly_instantaneous")]
        for var, val, unit, usrc, stat in items:
            if val is not None:
                rows.append({"location": location, "latitude": lat, "longitude": lon, "date": ts, "variable": var,
                             "value": float(val), "unit": unit, "unit_source": usrc, "statistic": stat,
                             "source": "Agromonitoring weather history",
                             "data_kind": "blended_measured_and_model_unverified"})
    from earthscope.ingest.power import STANDARD_COLUMNS
    return pd.DataFrame(rows, columns=STANDARD_COLUMNS)


def parse_ndvi_history(payload, polygon_id, location, lat, lon):
    """One row per satellite acquisition. Cloud percentage and useful area are kept so cloudy
    scenes can be excluded explicitly during analysis. Entries without 'data' are skipped and counted."""
    if not isinstance(payload, list):
        raise ValueError("ndvi/history response is not a list")
    rows, skipped = [], 0
    for e in payload:
        d = e.get("data")
        if not d or d.get("mean") is None:
            skipped += 1
            continue
        rows.append({"polygon_id": polygon_id, "location": location, "latitude": lat, "longitude": lon,
                     "date": pd.to_datetime(e["dt"], unit="s", utc=True).tz_localize(None),
                     "satellite": e.get("source"), "cloud_pct": e.get("cl"), "useful_area_pct": e.get("dc"),
                     "ndvi_mean": d.get("mean"), "ndvi_median": d.get("median"), "ndvi_p25": d.get("p25"),
                     "ndvi_p75": d.get("p75"), "ndvi_min": d.get("min"), "ndvi_max": d.get("max"),
                     "ndvi_std": d.get("std"), "n_pixels": d.get("num"),
                     "source": "Agromonitoring NDVI history", "data_kind": "satellite_derived", "unit": "1"})
    df = pd.DataFrame(rows, columns=NDVI_COLUMNS)
    if df.duplicated(["date", "satellite"], keep=False).any():
        g = df[df.duplicated(["date", "satellite"], keep=False)].groupby(["date", "satellite"])["ndvi_mean"]
        if g.nunique().gt(1).any():
            raise ValueError("conflicting NDVI values for the same date and satellite")
        df = df.drop_duplicates(["date", "satellite"])
    df.attrs["entries_skipped_without_data"] = skipped
    return df
