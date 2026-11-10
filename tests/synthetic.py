"""SYNTHETIC TEST FIXTURES ONLY.
Every payload carries SYNTHETIC in its header, so the pipeline labels the rows
'SYNTHETIC TEST DATA' and the dashboard shows a warning. Never use as real data.
Pass real_looking=True to build a payload WITHOUT that marker, used only to verify that
the pipeline would label genuine NASA data differently (still never real data)."""
import json

import numpy as np

VARS = {"T2M": "C", "PRECTOTCORR": "mm/day", "RH2M": "%", "WS10M": "m/s"}
BASE = {"T2M": 27, "PRECTOTCORR": 3, "RH2M": 70, "WS10M": 3}


def make_payload(lat, lon, start=1981, end=2020, trend=0.03, seed=0, missing=(), bad=(), noise=0.3,
                 units="default", param_meta=None, header_extra=None, real_looking=False, drop_years=(),
                 drop_months=()):
    """trend applies to T2M only (units per year). drop_years removes whole years; drop_months removes
    (year, month) keys, so they are ABSENT from the file (not -999)."""
    params = {}
    for vi, var in enumerate(VARS):
        series = {}
        for y in range(start, end + 1):
            if y in drop_years:
                continue
            for mth in range(1, 13):
                if (y, mth) in drop_months:
                    continue
                seas = 2 * np.sin(2 * np.pi * mth / 12)
                tr = trend * (y - start) if var == "T2M" else 0.0
                eps = np.random.default_rng([seed, y, mth, vi]).normal(0, noise) if noise else 0.0
                series[f"{y}{mth:02d}"] = round(BASE[var] + seas + tr + eps, 6)
            series[f"{y}13"] = 0.0
        params[var] = series
    for var, key in missing:
        params[var][key] = -999.0
    for var, key, val in bad:
        params[var][key] = val
    header = {"title": "test fixture" if real_looking else "SYNTHETIC TEST FIXTURE, not NASA data",
              "fill_value": -999.0, "start": start, "end": end}
    header.update(header_extra or {})
    payload = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat, 10.0]},
               "properties": {"parameter": params}, "header": header}
    if units == "default":
        payload["parameters"] = {v: {"units": u, "longname": f"{v} long name"} for v, u in VARS.items()}
    elif units is not None:
        payload["parameters"] = {v: {"units": units.get(v)} for v in VARS}
    if param_meta:
        payload.setdefault("parameters", {})
        for v, extra in param_meta.items():
            payload["parameters"].setdefault(v, {}).update(extra)
    return payload


def write_json(path, *a, **k):
    path.write_text(json.dumps(make_payload(*a, **k)))
    return path


def make_csv(lat, lon, start=1981, end=2000, trend=0.03, seed=0, dup_rows=(), with_units=True):
    """dup_rows: list of (var, year, delta). A duplicated table row is appended; delta is added to JAN."""
    p = make_payload(lat, lon, start, end, trend, seed)["properties"]["parameter"]
    lines = ["-BEGIN HEADER-", "SYNTHETIC TEST FIXTURE laid out like a POWER monthly CSV",
             f"Location: Latitude  {lat}  Longitude {lon}", "Elevation: 10 meters",
             "Missing values are filled with fill value -999"]
    if with_units:
        lines += ["T2M     Synthetic Temperature at 2 Meters (C)", "PRECTOTCORR     Synthetic Precipitation (mm/day)"]
    lines += ["-END HEADER-", "PARAMETER,YEAR,JAN,FEB,MAR,APR,MAY,JUN,JUL,AUG,SEP,OCT,NOV,DEC,ANN"]
    for var in ("T2M", "PRECTOTCORR"):
        for y in range(start, end + 1):
            vals = [p[var][f"{y}{m:02d}"] for m in range(1, 13)]
            lines.append(f"{var},{y}," + ",".join(str(v) for v in vals) + ",0.0")
    for var, y, delta in dup_rows:
        vals = [p[var][f"{y}{m:02d}"] for m in range(1, 13)]
        vals[0] += delta
        lines.append(f"{var},{y}," + ",".join(str(v) for v in vals) + ",0.0")
    return "\n".join(lines)


def make_power_like(lat, lon, start=1981, end=2020, seed=0, sources=None, header_end=None):
    """SYNTHETIC fixture laid out like a real Data Access Viewer response: seven parameters, 2 decimal
    rounding, a month-13 annual value (day-weighted mean for mean parameters, max/min for T2M_MAX/T2M_MIN),
    and a full header. Title contains SYNTHETIC so the pipeline labels every row as test data."""
    import calendar
    units = {"T2M": "C", "T2M_MAX": "C", "T2M_MIN": "C", "PRECTOTCORR": "mm/day", "RH2M": "%", "WS10M": "m/s",
             "ALLSKY_SFC_SW_DWN": "kW-hr/m^2/day"}
    names = {"T2M": "Temperature at 2 Meters", "T2M_MAX": "Temperature at 2 Meters Maximum",
             "T2M_MIN": "Temperature at 2 Meters Minimum", "PRECTOTCORR": "Precipitation Corrected",
             "RH2M": "Relative Humidity at 2 Meters", "WS10M": "Wind Speed at 10 Meters",
             "ALLSKY_SFC_SW_DWN": "All Sky Surface Shortwave Downward Irradiance"}
    par = {v: {} for v in units}
    for y in range(start, end + 1):
        dm = np.array([calendar.monthrange(y, m)[1] for m in range(1, 13)], float)
        vals = {v: [] for v in units}
        for m in range(1, 13):
            r = np.random.default_rng([seed, y, m, 7])
            t = 27 + 2 * np.sin(2 * np.pi * m / 12) + r.normal(0, 0.3)
            vals["T2M"].append(t)
            vals["T2M_MAX"].append(t + 3 + abs(r.normal(0, 0.3)))
            vals["T2M_MIN"].append(t - 3 - abs(r.normal(0, 0.3)))
            vals["PRECTOTCORR"].append(max(0.0, 3 + 2 * np.sin(2 * np.pi * m / 12) + r.normal(0, 0.5)))
            vals["RH2M"].append(70 + 5 * np.sin(2 * np.pi * m / 12) + r.normal(0, 1))
            vals["WS10M"].append(3 + r.normal(0, 0.2))
            vals["ALLSKY_SFC_SW_DWN"].append(5 + 0.5 * np.sin(2 * np.pi * m / 12) + r.normal(0, 0.1))
        for v in units:
            a = np.round(np.array(vals[v]), 2)
            for m in range(1, 13):
                par[v][f"{y}{m:02d}"] = float(a[m - 1])
            if v == "T2M_MAX":
                par[v][f"{y}13"] = float(a.max())
            elif v == "T2M_MIN":
                par[v][f"{y}13"] = float(a.min())
            else:
                par[v][f"{y}13"] = round(float((a * dm).sum() / dm.sum()), 2)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat, 27.76]},
            "properties": {"parameter": par},
            "header": {"title": "SYNTHETIC TEST FIXTURE laid out like NASA/POWER Source Native Resolution Monthly and Annual",
                       "api": {"version": "v2.10.0", "name": "POWER Monthly and Annual API"},
                       "sources": sources or ["SYN1DEG", "MERRA2", "SRB", "POWER"], "fill_value": -999, "time_standard": "LST",
                       "start": f"{start}0101", "end": f"{header_end or end}1231"},
            "messages": [], "parameters": {v: {"units": units[v], "longname": names[v]} for v in units}, "times": {"data": 0.4}}
