"""NASA POWER monthly point parsing and URL building.

Output of every parser is the standard long table (STANDARD_COLUMNS). Missing values are NaN.
Nothing is filled in or invented. Units come from the response metadata; see resolve_units.
Each returned DataFrame carries attrs["file_meta"], the response header and per-parameter
metadata copied verbatim, so provenance survives into the processed metadata file.
"""
import io
import json
import re

import pandas as pd

from earthscope import config

STANDARD_COLUMNS = ["location", "latitude", "longitude", "date", "variable", "value", "unit",
                    "unit_source", "statistic", "source", "data_kind"]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
DEFAULT_FILL = -999.0
SYNTHETIC_SOURCE = "SYNTHETIC TEST DATA"
POWER_SOURCE = "NASA POWER"
# gridded estimate from reanalysis and satellite based sources; never a station observation
POWER_KIND = "gridded_estimate_not_station_observation"
UNIT_FROM_RESPONSE = "response_metadata"
UNIT_ASSUMED = "assumed_documented_default"


class UnitError(ValueError):
    """Units missing from the response, or different from what this project expects."""


def build_url(lat, lon, start, end, parameters=None, fmt="JSON", community=None):
    parameters = parameters or config.POWER_PARAMS
    community = community or config.POWER_COMMUNITY
    return (f"{config.POWER_BASE}/monthly/point?parameters={','.join(parameters)}"
            f"&community={community}&longitude={lon}&latitude={lat}"
            f"&start={start}&end={end}&format={fmt}")


# ------------------------------------------------------------------ units and semantics
VIEWER_PATTERN = re.compile(
    r"^POWER_Point_Monthly_(?P<start>\d{8})_(?P<end>\d{8})_(?P<lat>\d{3}d\d{2})(?P<ns>[NS])_"
    r"(?P<lon>\d{3}d\d{2})(?P<ew>[EW])_(?P<tstd>[A-Za-z]+)_(?P<loc>.+)\.(?P<ext>json|csv)$", re.I)


def parse_viewer_filename(name):
    """Facts embedded in a POWER Data Access Viewer file name, or None if the name has another form.
    Example: POWER_Point_Monthly_19810101_20251231_005d62N_000d17W_LST_Accra.json"""
    m = VIEWER_PATTERN.match(name)
    if not m:
        return None
    lat = float(m["lat"].replace("d", ".")) * (1 if m["ns"].upper() == "N" else -1)
    lon = float(m["lon"].replace("d", ".")) * (1 if m["ew"].upper() == "E" else -1)
    return {"location": m["loc"], "latitude": lat, "longitude": lon, "start": m["start"], "end": m["end"],
            "time_standard": m["tstd"].upper(), "format": m["ext"].lower()}


def normalise_unit(raw):
    return config.UNIT_ALIASES.get(str(raw).strip().lower())


def resolve_units(var, raw, assume_documented=False):
    """Return (unit, unit_source). Units are taken from the response; they are compared with the
    expected unit; a missing or different unit raises UnitError."""
    expected = config.EXPECTED_UNITS.get(var)
    if raw is None or str(raw).strip() == "":
        if assume_documented and expected:
            return expected, UNIT_ASSUMED
        raise UnitError(f"{var}: the response metadata states no units. Inspect the file with "
                        "scripts/inspect_file.py. Use --assume-documented-units only after confirming "
                        f"the documented unit ({expected}) yourself.")
    unit = normalise_unit(raw)
    if unit is None:
        raise UnitError(f"{var}: unrecognised unit '{raw}' in the response (expected {expected}). "
                        "Nothing is converted automatically.")
    if expected and unit != expected:
        raise UnitError(f"{var}: response unit '{raw}' differs from the expected '{expected}'. "
                        "Nothing is converted automatically.")
    return unit, UNIT_FROM_RESPONSE


def statistic_for(var):
    return config.VARIABLE_SEMANTICS.get(var, ("unknown", "unknown"))[1]


def find_resolution(obj):
    """Return a resolution value only if the response itself states one (any key containing 'resol')."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "resol" in str(k).lower() and v not in (None, "", {}):
                return v
            found = find_resolution(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_resolution(v)
            if found is not None:
                return found
    return None


def _source_label(header_text):
    return SYNTHETIC_SOURCE if "SYNTHETIC" in header_text.upper() else POWER_SOURCE


# ------------------------------------------------------------------ metadata and structure
def extract_metadata_json(payload):
    header = payload.get("header", {}) or {}
    return {"format": "json", "header": header, "parameters": payload.get("parameters", {}) or {},
            "geometry": payload.get("geometry"), "fill_value": header.get("fill_value"),
            "requested_start": header.get("start"), "requested_end": header.get("end"),
            "resolution_stated_in_response": find_resolution(payload)}


def extract_metadata_csv(text):
    header = text.split("-END HEADER-", 1)[0] if "-END HEADER-" in text else ""
    dates = re.search(r"(\d{2}/\d{2}/\d{4})\s+through\s+(\d{2}/\d{2}/\d{4})", header)
    params = {}
    for line in header.splitlines():
        m = re.match(r"^\s*(\w+)\s+(.*)$", line)
        if m and m.group(1).isupper() and "(" in m.group(2):
            params[m.group(1)] = line.strip()
    return {"format": "csv", "header_text": header.strip(), "parameter_lines": params,
            "requested_start": dates.group(1) if dates else None,
            "requested_end": dates.group(2) if dates else None,
            "resolution_stated_in_response": ("stated in header text" if re.search("resolution", header, re.I) else None)}


def file_coordinates(text, ext):
    """Coordinates stated inside a raw file, or None."""
    if ext == "json":
        try:
            c = json.loads(text).get("geometry", {}).get("coordinates")
        except Exception:
            return None
        return (float(c[1]), float(c[0])) if c else None
    m = re.search(r"Latitude\s+(-?\d+\.?\d*)\s+Longitude\s+(-?\d+\.?\d*)", text)
    return (float(m.group(1)), float(m.group(2))) if m else None


def validate_structure(text, fmt):
    """Structural check only (used before saving a download). Unit checks happen at processing."""
    if fmt.upper() == "JSON":
        p = json.loads(text)
        if not p.get("properties", {}).get("parameter"):
            raise ValueError(f"Not a POWER monthly point JSON (top level keys: {list(p)[:6]})")
    elif not re.search(r"PARAMETER\s*,\s*YEAR", text):
        raise ValueError("Not a POWER monthly point CSV: no PARAMETER,YEAR table found")


# ------------------------------------------------------------------ parsers
def _finish(rows, location, lat, lon, units, source, meta, assume):
    df = pd.DataFrame(rows, columns=["date", "variable", "value"])
    resolved = {v: resolve_units(v, units.get(v), assume) for v in df["variable"].unique()}
    df["location"], df["latitude"], df["longitude"] = location, lat, lon
    df["unit"] = df["variable"].map(lambda v: resolved[v][0])
    df["unit_source"] = df["variable"].map(lambda v: resolved[v][1])
    df["statistic"] = df["variable"].map(statistic_for)
    df["source"] = source
    df["data_kind"] = POWER_KIND if source == POWER_SOURCE else "synthetic_test"
    out = df[STANDARD_COLUMNS].sort_values(["variable", "date"]).reset_index(drop=True)
    out.attrs["file_meta"] = meta
    return out


def parse_json(payload, location, lat=None, lon=None, assume_documented_units=False):
    """Parse a POWER monthly point JSON response (dict or JSON string)."""
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    if "properties" not in payload or "parameter" not in payload["properties"]:
        raise ValueError("Not a POWER monthly point JSON: missing properties.parameter "
                         f"(top level keys: {list(payload)[:6]})")
    if lat is None or lon is None:
        coords = payload.get("geometry", {}).get("coordinates")
        if not coords:
            raise ValueError("No coordinates in file and none supplied")
        lon, lat = float(coords[0]), float(coords[1])
    meta = extract_metadata_json(payload)
    fill = float(meta["fill_value"]) if meta["fill_value"] is not None else DEFAULT_FILL
    units = {v: (m or {}).get("units") for v, m in meta["parameters"].items()}
    rows = []
    for var, series in payload["properties"]["parameter"].items():
        for key, val in series.items():
            year, month = int(key[:4]), int(key[4:])
            if month == 13:  # annual summary row
                continue
            v = float("nan") if (val is None or float(val) == fill) else float(val)
            rows.append((pd.Timestamp(year=year, month=month, day=1), var, v))
    return _finish(rows, location, lat, lon, units, _source_label(json.dumps(meta["header"])), meta,
                   assume_documented_units)


def parse_csv(text, location, lat=None, lon=None, assume_documented_units=False):
    """Parse a POWER monthly point CSV (header block, then PARAMETER,YEAR,JAN..DEC,ANN)."""
    if "-END HEADER-" in text:
        header, body = text.split("-END HEADER-", 1)
    else:
        header, body = "", text
    if lat is None or lon is None:
        c = file_coordinates(text, "csv")
        if not c:
            raise ValueError("No coordinates in CSV header and none supplied")
        lat, lon = c
    fm = re.search(r"fill value[^-\d]*(-?\d+\.?\d*)", header, re.I)
    fill = float(fm.group(1)) if fm else DEFAULT_FILL
    units = {}
    for line in header.splitlines():
        um = re.match(r"^\s*(\w+)\s+.*\(([^()]*)\)\s*$", line)
        if um and um.group(1).isupper():
            units[um.group(1)] = um.group(2)
    table = pd.read_csv(io.StringIO(body.strip()))
    table.columns = [c.strip().upper() for c in table.columns]
    need = {"PARAMETER", "YEAR"} | set(MONTHS)
    if not need.issubset(table.columns):
        raise ValueError(f"CSV is missing columns: {sorted(need - set(table.columns))}")
    rows = []
    for _, r in table.iterrows():
        for i, mon in enumerate(MONTHS, start=1):
            val = float(r[mon])
            rows.append((pd.Timestamp(year=int(r["YEAR"]), month=i, day=1), r["PARAMETER"],
                         float("nan") if val == fill else val))
    return _finish(rows, location, lat, lon, units, _source_label(header), extract_metadata_csv(text),
                   assume_documented_units)
