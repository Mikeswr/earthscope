"""Raw files -> standardised, QC-flagged dataset + provenance sidecar."""
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path

import pandas as pd

from earthscope import config
from earthscope.ingest import power
from earthscope.qc import checks

RAW_PATTERN = re.compile(r"^power_monthly_(?P<loc>.+)_(?P<start>\d{4})_(?P<end>\d{4})\.(?P<ext>json|csv)$", re.I)
PROCESSED_NAME = "power_monthly_standardised.csv"
METADATA_NAME = "power_monthly_metadata.json"
FETCH_SUFFIX = ".fetch.json"   # written by scripts/fetch_power.py next to each raw file
IMPORT_SUFFIX = ".import.json"  # written by import_files: original file name, checksum and how the location was identified


def canonical_name(location, start, end, ext):
    return f"power_monthly_{location}_{start}_{end}.{ext.lower().lstrip('.')}"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_file(path, locations, location=None, assume_documented_units=False):
    """Parse one raw file. Location comes from the argument, the file name, or the coordinates
    stated in the file. A named location is cross-checked against the file's own coordinates."""
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    if ext not in ("json", "csv"):
        raise ValueError(f"{path.name}: only .json and .csv are supported")
    text = path.read_text(encoding="utf-8")
    m = RAW_PATTERN.match(path.name)
    viewer = power.parse_viewer_filename(path.name)
    name = location or (m.group("loc") if m else None) or (viewer["location"] if viewer else None)
    coords = power.file_coordinates(text, ext)
    if viewer and coords and (abs(viewer["latitude"] - coords[0]) > 0.011 or abs(viewer["longitude"] - coords[1]) > 0.011):
        raise ValueError(f"{path.name}: the coordinates in the file name ({viewer['latitude']}, {viewer['longitude']}) "
                         f"do not match the coordinates inside the file {coords}. Not importing.")
    lookup = {k.lower(): k for k in locations}
    if name:
        if name.lower() not in lookup:
            raise ValueError(f"{path.name}: location '{name}' is not in locations.yaml ({', '.join(locations)})")
        name = lookup[name.lower()]
        cfg_lat, cfg_lon = locations[name]
        if coords and abs(coords[0] - cfg_lat) + abs(coords[1] - cfg_lon) > 1.0:
            raise ValueError(f"{path.name}: coordinates in file {coords} do not match {name} "
                             f"({cfg_lat}, {cfg_lon}). Wrong file or wrong location name.")
        lat, lon = coords or (cfg_lat, cfg_lon)
    else:
        if not coords:
            raise ValueError(f"{path.name}: no location in the file name and no coordinates in the file. "
                             "Pass --location or rename it power_monthly_<Location>_<start>_<end>.json")
        name = _nearest(coords[0], coords[1], locations, path.name)
        lat, lon = coords
    parser = power.parse_json if ext == "json" else power.parse_csv
    df = parser(text, name, lat, lon, assume_documented_units=assume_documented_units)
    df.attrs["file_info"] = {"name": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path),
                             "format": ext}
    return df


def _nearest(lat, lon, locations, fname):
    best = min(locations.items(), key=lambda kv: abs(kv[1][0] - lat) + abs(kv[1][1] - lon))
    d = abs(best[1][0] - lat) + abs(best[1][1] - lon)
    if d > 1.0:
        raise ValueError(f"{fname}: coordinates ({lat}, {lon}) are not near any configured location. "
                         "Rename the file power_monthly_<Location>_<start>_<end>.json or pass --location.")
    return best[0]


def _file_record(df, raw_dir):
    """Provenance for one raw file: verbatim response metadata plus the ACTUAL coverage."""
    info, meta = dict(df.attrs["file_info"]), df.attrs["file_meta"]
    sidecar = Path(raw_dir) / (info["name"] + FETCH_SUFFIX)
    info["fetch_record"] = json.loads(sidecar.read_text()) if sidecar.exists() else None
    imp = Path(raw_dir) / (info["name"] + IMPORT_SUFFIX)
    info["import_record"] = json.loads(imp.read_text()) if imp.exists() else None
    info["time_standard"] = (meta.get("header") or {}).get("time_standard")
    info["header_sources_sorted"] = sorted((meta.get("header") or {}).get("sources") or [])
    geo = meta.get("geometry") or {}
    info["elevation_value_in_file_m"] = (geo.get("coordinates") or [None, None, None])[2] if geo else None
    info["location"] = df["location"].iat[0]
    info["latitude_in_file_or_config"], info["longitude_in_file_or_config"] = df["latitude"].iat[0], df["longitude"].iat[0]
    info["response_metadata"] = meta
    info["requested_start"], info["requested_end"] = meta.get("requested_start"), meta.get("requested_end")
    cov = {}
    for var, g in df.groupby("variable"):
        valid = g[g["value"].notna()]
        span = pd.date_range(g["date"].min(), g["date"].max(), freq="MS")
        cov[var] = {"first_month_present": str(g["date"].min().date()), "last_month_present": str(g["date"].max().date()),
                    "first_valid_month": str(valid["date"].min().date()) if len(valid) else None,
                    "last_valid_month": str(valid["date"].max().date()) if len(valid) else None,
                    "n_months_present": int(len(g)), "n_valid": int(len(valid)),
                    "n_missing_values": int(len(g) - len(valid)),
                    "months_absent_inside_span": int(len(span.difference(pd.DatetimeIndex(g["date"]))))}
    info["actual_coverage"] = cov
    return info


def build_processed(raw_dir=None, out_dir=None, locations=None, assume_documented_units=False):
    """Read every canonical raw file, merge, flag, write CSV and metadata. Returns the DataFrame."""
    raw_dir = Path(raw_dir) if raw_dir else config.raw_dir()
    out_dir = Path(out_dir) if out_dir else config.processed_dir()
    locations = locations or config.load_locations()
    files = sorted(p for p in raw_dir.iterdir() if RAW_PATTERN.match(p.name))
    if not files:
        raise FileNotFoundError(f"No files named power_monthly_<Location>_<start>_<end>.json/csv in {raw_dir}")
    frames = [parse_file(p, locations, assume_documented_units=assume_documented_units) for p in files]
    records = [_file_record(f, raw_dir) for f in frames]
    df = pd.concat(frames, ignore_index=True)
    # one unit and one statistic per variable across all files
    for col in ("unit", "statistic"):
        bad = df.groupby("variable")[col].nunique()
        if (bad > 1).any():
            raise ValueError(f"variable(s) {list(bad[bad > 1].index)} have more than one {col} across raw files")
    n_before = len(df)
    dup = df.duplicated(["location", "variable", "date"], keep=False)
    if dup.any():
        # identical repeats are collapsed and counted; conflicting values are an error, never a silent pick
        g = df[dup].groupby(["location", "variable", "date"])["value"]
        conflict = g.apply(lambda s: s.dropna().nunique() > 1 or (s.isna().any() and s.notna().any()))
        if conflict.any():
            raise ValueError(f"{int(conflict.sum())} month(s) have conflicting values across or within raw files")
        df = df.drop_duplicates(["location", "variable", "date"])
    removed = n_before - len(df)
    df = checks.add_qc_flag(df).sort_values(["location", "variable", "date"]).reset_index(drop=True)
    df.to_csv(out_dir / PROCESSED_NAME, index=False)

    variables = {}
    for var, g in df.groupby("variable"):
        stated = [r["response_metadata"].get("parameters", {}).get(var) or
                  r["response_metadata"].get("parameter_lines", {}).get(var) for r in records
                  if r["location"] in set(g["location"])]
        variables[var] = {
            "unit": g["unit"].iat[0], "unit_source": sorted(g["unit_source"].unique()),
            "statistic": g["statistic"].iat[0],
            "semantics_status": config.SEMANTICS_STATUS,
            "quantity": config.VARIABLE_SEMANTICS.get(var, ("unknown",))[0],
            "response_parameter_metadata_verbatim": next((s for s in stated if s), None),
            "spatial_resolution": next((r["response_metadata"]["resolution_stated_in_response"] for r in records
                                        if r["response_metadata"].get("resolution_stated_in_response")),
                                       "not stated in the response; not verified"),
        }
    meta = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "files": records,
        "variables": variables,
        "sources": sorted(df["source"].unique()),
        "data_kind": sorted(df["data_kind"].unique()),
        "temporal_resolution": "monthly",
        "community": config.POWER_COMMUNITY,
        "duplicates_removed": int(removed),
        "assumed_documented_units_used": bool((df["unit_source"] == power.UNIT_ASSUMED).any()),
        "rows": int(len(df)),
        "note": "POWER values are model based estimates, not direct station observations.",
    }
    (out_dir / METADATA_NAME).write_text(json.dumps(meta, indent=2, default=str))
    return df


def import_files(paths, location=None, locations=None, raw_dir=None, assume_documented_units=False):
    """Copy user downloaded files into data/raw under the canonical name (after parsing them)."""
    locations = locations or config.load_locations()
    raw_dir = Path(raw_dir) if raw_dir else config.raw_dir()
    copied = []
    for p in map(Path, paths):
        df = parse_file(p, locations, location=location, assume_documented_units=assume_documented_units)
        years = df["date"].dt.year
        dest = raw_dir / canonical_name(df["location"].iat[0], years.min(), years.max(), p.suffix)
        if dest.resolve() != p.resolve():
            shutil.copyfile(p, dest)
            viewer = power.parse_viewer_filename(p.name)
            (dest.parent / (dest.name + IMPORT_SUFFIX)).write_text(json.dumps({
                "original_filename": p.name, "original_sha256": _sha256(p),
                "imported_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "location_identified_from": ("argument" if location else "viewer file name and file coordinates" if viewer
                                             else "canonical file name or file coordinates"),
                "file_name_facts": viewer}, indent=2))
        copied.append(dest)
    return copied
