"""OpenWeather clients (key from OPENWEATHER_API_KEY, see docs/CREDENTIALS.md).

STATUS: written from the OpenWeather documentation and NOT yet tested against live responses.
VERIFIED_AGAINST_LIVE_API stays False until scripts/check_apis.py has succeeded with your key.

Endpoints (entitlements differ; the key you hold may not include all of them):
  current_weather  GET api.openweathermap.org/data/2.5/weather              free plan
  day_summary      GET api.openweathermap.org/data/3.0/onecall/day_summary  One Call 3.0 subscription;
                   daily aggregates from 1979-01-02 per the documentation
  history_hourly   GET history.openweathermap.org/data/2.5/history/city     Professional/Expert plans;
                   hourly data, availability depends on subscription
Field names below follow secondary copies of the documentation and must be confirmed by the probe.
"""
import pandas as pd

from earthscope import config
from earthscope.ingest import http
from earthscope.ingest.power import STANDARD_COLUMNS

VERIFIED_AGAINST_LIVE_API = False
CURRENT = "https://api.openweathermap.org/data/2.5/weather"
ONECALL = "https://api.openweathermap.org/data/3.0/onecall"
HISTORY = "https://history.openweathermap.org/data/2.5/history/city"
KIND = "blended_measured_and_model_unverified"


def _key():
    return config.get_key(config.ENV_OPENWEATHER)


def current_weather(lat, lon, units="metric", **kw):
    return http.call("GET", CURRENT, secret=_key(), params={"lat": lat, "lon": lon, "units": units}, **kw)[1]


def day_summary(lat, lon, date, units="metric", **kw):
    """date: 'YYYY-MM-DD'."""
    return http.call("GET", f"{ONECALL}/day_summary", secret=_key(),
                     params={"lat": lat, "lon": lon, "date": date, "units": units}, **kw)[1]


def history_hourly(lat, lon, start_unix, end_unix, units="metric", **kw):
    return http.call("GET", HISTORY, secret=_key(), params={
        "lat": lat, "lon": lon, "type": "hour", "start": int(start_unix), "end": int(end_unix), "units": units}, **kw)[1]


def _rows(date, items, location, lat, lon, source, statistic_default, unit_source):
    rows = []
    for var, value, unit, stat in items:
        if value is None:
            continue   # absent is not zero; nothing is filled in
        rows.append({"location": location, "latitude": lat, "longitude": lon, "date": date, "variable": var,
                     "value": float(value), "unit": unit, "unit_source": unit_source,
                     "statistic": stat or statistic_default, "source": source, "data_kind": KIND})
    return rows


def _check_units(payload, units):
    if units != "metric":
        raise ValueError("only units='metric' is supported")
    echoed = payload.get("units")
    if echoed is not None and echoed != "metric":
        raise http.ApiError(200, f"response says units='{echoed}' but metric was requested", "unit mismatch")
    return "response_echo_metric" if echoed == "metric" else "assumed_from_request_units_metric"


def parse_day_summary(payload, location, lat, lon, units="metric"):
    unit_source = _check_units(payload, units)
    g = lambda *path: _dig(payload, path)
    items = [
        ("temp_min", g("temperature", "min"), "C", "daily_minimum"),
        ("temp_max", g("temperature", "max"), "C", "daily_maximum"),
        ("temp_morning", g("temperature", "morning"), "C", "time_of_day_value"),
        ("temp_afternoon", g("temperature", "afternoon"), "C", "time_of_day_value"),
        ("temp_evening", g("temperature", "evening"), "C", "time_of_day_value"),
        ("temp_night", g("temperature", "night"), "C", "time_of_day_value"),
        ("precip_total", g("precipitation", "total"), "mm", "daily_total"),
        ("humidity_afternoon", g("humidity", "afternoon"), "%", "time_of_day_value"),
        ("pressure_afternoon", g("pressure", "afternoon"), "hPa", "time_of_day_value"),
        ("cloud_cover_afternoon", g("cloud_cover", "afternoon"), "%", "time_of_day_value"),
        ("wind_max_speed", g("wind", "max", "speed"), "m/s", "daily_maximum"),
    ]
    if "date" not in payload:
        raise ValueError("day_summary response has no 'date' field")
    rows = _rows(pd.Timestamp(payload["date"]), items, location, lat, lon,
                 "OpenWeather One Call 3.0 day_summary", "daily_aggregate", unit_source)
    return pd.DataFrame(rows, columns=STANDARD_COLUMNS)


def parse_history_hourly(payload, location, lat, lon, units="metric"):
    unit_source = _check_units(payload, units)
    if "list" not in payload:
        raise ValueError("history response has no 'list' field")
    rows = []
    for e in payload["list"]:
        ts = pd.to_datetime(e["dt"], unit="s", utc=True).tz_localize(None)
        items = [("temp", _dig(e, ("main", "temp")), "C", "hourly_instantaneous"),
                 ("pressure", _dig(e, ("main", "pressure")), "hPa", "hourly_instantaneous"),
                 ("humidity", _dig(e, ("main", "humidity")), "%", "hourly_instantaneous"),
                 ("wind_speed", _dig(e, ("wind", "speed")), "m/s", "hourly_instantaneous"),
                 ("cloud_cover", _dig(e, ("clouds", "all")), "%", "hourly_instantaneous"),
                 ("rain_1h", _dig(e, ("rain", "1h")), "mm", "hourly_accumulation")]
        rows += _rows(ts, items, location, lat, lon, "OpenWeather History API", "hourly", unit_source)
    return pd.DataFrame(rows, columns=STANDARD_COLUMNS)


def _dig(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d
