"""Pre-import validation of NASA POWER monthly point files.

validate_file inspects one file WITHOUT importing it and returns every check with a status
(pass, warn, fail, info) and the numbers behind it. compare_files looks across files.
Nothing here changes data. Interpretation checks (what the monthly and annual numbers mean) are
evidence from the returned values, not proof; the NASA documentation is the source of the definitions.
"""
import calendar
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from earthscope import config
from earthscope.ingest import power
from earthscope.qc import checks

ROUNDING_TOL = 0.0055      # annual vs monthly aggregate comparison (values are rounded to 2 decimals)
EXTREME_TOL = 1e-6         # annual max/min must equal the max/min of the months exactly
COORD_TOL_DEG = 0.011      # file name coordinates are rounded to 2 decimals


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_json_strict(text):
    """json.loads that also reports duplicated keys (plain json.loads silently keeps the last one)."""
    dups = []

    def hook(pairs):
        seen = set()
        for k, _ in pairs:
            if k in seen:
                dups.append(k)
            seen.add(k)
        return dict(pairs)
    return json.loads(text, object_pairs_hook=hook), dups


class _Checks(list):
    def add(self, name, status, detail="", **data):
        self.append({"check": name, "status": status, "detail": detail, **data})


def _expected_keys(header):
    try:
        y0, y1 = int(str(header["start"])[:4]), int(str(header["end"])[:4])
    except (KeyError, ValueError, TypeError):
        return None
    return {f"{y}{m:02d}" for y in range(y0, y1 + 1) for m in range(1, 14)}


def annual_consistency(series, fill):
    """Compare the month-13 (annual) value with several ways of aggregating the twelve months."""
    out = {"simple": [], "weighted": [], "max": [], "min": []}
    years = sorted({int(k[:4]) for k in series})
    for y in years:
        vals = [series.get(f"{y}{m:02d}") for m in range(1, 13)]
        ann = series.get(f"{y}13")
        if ann is None or ann == fill or any(v is None or v == fill for v in vals):
            continue
        a, d = np.array(vals, float), np.array([calendar.monthrange(y, m)[1] for m in range(1, 13)], float)
        out["simple"].append(abs(ann - a.mean()))
        out["weighted"].append(abs(ann - (a * d).sum() / d.sum()))
        out["max"].append(abs(ann - a.max()))
        out["min"].append(abs(ann - a.min()))
    n = len(out["simple"])
    return {"n_years_compared": n,
            **{f"max_abs_diff_{k}": (float(max(v)) if v else None) for k, v in out.items()}}


def validate_file(path, locations=None, requested=None):
    path = Path(path)
    locations = locations or config.load_locations()
    requested = list(requested or config.POWER_PARAMS)
    text = path.read_text(encoding="utf-8")
    res = {"file": path.name, "bytes": len(text.encode("utf-8")), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    c = _Checks()
    try:
        doc, dups = load_json_strict(text)
    except ValueError as e:
        c.add("json_parses", "fail", str(e))
        res.update(checks=list(c), status="fail")
        return res
    c.add("json_parses", "pass")
    c.add("no_duplicate_keys", "fail" if dups else "pass", f"duplicated keys: {sorted(set(dups))[:10]}" if dups else "")

    # ---- structure
    geo, props, header, params = doc.get("geometry"), doc.get("properties", {}), doc.get("header", {}) or {}, doc.get("parameters", {}) or {}
    series = props.get("parameter") if isinstance(props, dict) else None
    ok = (doc.get("type") == "Feature" and isinstance(geo, dict) and geo.get("type") == "Point"
          and len(geo.get("coordinates", [])) >= 2 and isinstance(series, dict) and series)
    c.add("is_power_point_feature", "pass" if ok else "fail",
          "" if ok else f"top level keys {list(doc)[:8]}; need type=Feature, geometry Point, properties.parameter")
    if not ok:
        res.update(checks=list(c), status="fail")
        return res
    for k in ("fill_value", "start", "end"):
        c.add(f"header_has_{k}", "pass" if k in header else "fail")
    for k in ("title", "api", "sources", "time_standard"):
        c.add(f"header_has_{k}", "pass" if k in header else "warn")
    res["header"] = header
    res["messages"] = doc.get("messages")
    fill = float(header.get("fill_value", power.DEFAULT_FILL))

    # ---- requested versus returned parameters, and the parameter metadata
    got = sorted(series)
    missing_req, extra = [p for p in requested if p not in got], [p for p in got if p not in requested]
    c.add("all_requested_parameters_returned", "fail" if missing_req else "pass", f"missing: {missing_req}" if missing_req else "",
          requested=requested, returned=got)
    c.add("extra_parameters_returned", "info" if extra else "pass", f"returned but not requested: {extra}" if extra else "")
    meta_missing = [v for v in got if not isinstance(params.get(v), dict) or not params[v].get("units")]
    c.add("every_parameter_has_units_metadata", "fail" if meta_missing else "pass", f"no units for {meta_missing}" if meta_missing else "")
    unit_rows = {}
    for v in got:
        raw = (params.get(v) or {}).get("units")
        norm = power.normalise_unit(raw) if raw else None
        exp = config.EXPECTED_UNITS.get(v)
        status = "fail" if (raw is None or norm is None or (exp and norm != exp)) else ("pass" if exp else "warn")
        unit_rows[v] = {"units_in_response": raw, "longname": (params.get(v) or {}).get("longname"), "expected": exp, "status": status}
        c.add(f"units_{v}", status, f"response '{raw}', expected '{exp}'")
    res["parameter_metadata"] = unit_rows

    # ---- keys and coverage
    key_sets = {v: set(s) for v, s in series.items()}
    same_keys = len({frozenset(k) for k in key_sets.values()}) == 1
    c.add("all_parameters_share_one_key_set", "pass" if same_keys else "fail")
    bad_keys = sorted({k for ks in key_sets.values() for k in ks if not (len(k) == 6 and k.isdigit() and 1 <= int(k[4:]) <= 13)})
    c.add("keys_are_YYYYMM_with_month_1_to_13", "fail" if bad_keys else "pass", f"bad keys: {bad_keys[:5]}" if bad_keys else "")
    exp_keys = _expected_keys(header)
    coverage = {}
    for v, s in series.items():
        monthly = sorted(k for k in s if k[4:] != "13")
        vals = {k: s[k] for k in monthly}
        n_fill = sum(1 for x in vals.values() if x is not None and float(x) == fill)
        n_null = sum(1 for x in vals.values() if x is None)
        nonnum = [k for k, x in vals.items() if x is not None and not isinstance(x, (int, float))]
        valid = [k for k, x in vals.items() if x is not None and not isinstance(x, str) and float(x) != fill]
        absent = sorted(k for k in (exp_keys or set()) if k[4:] != "13" and k not in s)
        fill_keys = sorted(k for k, x in vals.items() if x is not None and float(x) == fill)
        years_with_fill = sorted({int(k[:4]) for k in fill_keys})
        coverage[v] = {"first_key": monthly[0], "last_key": monthly[-1], "n_monthly_keys": len(monthly),
                       "n_fill_values": n_fill, "n_null": n_null, "n_non_numeric": len(nonnum),
                       "n_absent_keys_vs_header_range": len(absent), "first_valid": valid[0] if valid else None,
                       "last_valid": valid[-1] if valid else None, "first_fill_key": fill_keys[0] if fill_keys else None,
                       "last_fill_key": fill_keys[-1] if fill_keys else None, "years_with_any_fill": years_with_fill,
                       "annual_keys_present": sum(1 for k in s if k[4:] == "13")}
        c.add(f"coverage_{v}", "pass" if not (n_fill or n_null or nonnum or absent) else "warn",
              f"{len(monthly)} monthly keys, {n_fill} fill values, {len(absent)} absent keys")
    res["coverage"] = coverage
    if exp_keys is not None:
        got_keys = set().union(*key_sets.values())
        c.add("returned_keys_cover_the_requested_header_range", "pass" if not (exp_keys - got_keys) else "fail",
              f"{len(exp_keys - got_keys)} expected keys absent" if exp_keys - got_keys else "",
              header_start=header.get("start"), header_end=header.get("end"),
              first_returned=min(got_keys), last_returned=max(got_keys))
        c.add("no_keys_outside_the_header_range", "pass" if not (got_keys - exp_keys) else "warn", f"{len(got_keys - exp_keys)} unexpected")
    annual_missing = {v: [y for y in sorted({int(k[:4]) for k in s}) if f"{y}13" not in s] for v, s in series.items()}
    c.add("every_year_has_an_annual_key", "pass" if not any(annual_missing.values()) else "warn")

    # ---- coordinates and location identity
    lon, lat = float(geo["coordinates"][0]), float(geo["coordinates"][1])
    elev = geo["coordinates"][2] if len(geo["coordinates"]) > 2 else None
    viewer = power.parse_viewer_filename(path.name)
    named = viewer["location"] if viewer else None
    nearest = min(locations, key=lambda n: haversine_km(lat, lon, *locations[n]))
    ident = {"file_latitude": lat, "file_longitude": lon, "elevation_value_in_file_m": elev,
             "filename_latitude": viewer["latitude"] if viewer else None, "filename_longitude": viewer["longitude"] if viewer else None,
             "location_named_in_filename": named, "nearest_configured_location": nearest,
             "distance_to_nearest_configured_km": round(haversine_km(lat, lon, *locations[nearest]), 2)}
    if named and named in locations:
        ident["distance_to_named_configured_km"] = round(haversine_km(lat, lon, *locations[named]), 2)
    res["location_identity"] = ident
    if viewer:
        match = abs(viewer["latitude"] - lat) <= COORD_TOL_DEG and abs(viewer["longitude"] - lon) <= COORD_TOL_DEG
        c.add("filename_coordinates_match_file_coordinates", "pass" if match else "fail", f"name {viewer['latitude']},{viewer['longitude']} vs file {lat},{lon}")
        c.add("filename_time_standard_matches_header", "pass" if viewer["time_standard"] == str(header.get("time_standard", "")).upper() else "warn")
        c.add("filename_range_matches_header", "pass" if (viewer["start"], viewer["end"]) == (str(header.get("start")), str(header.get("end"))) else "warn")
    if named:
        agree = named == nearest and ident.get("distance_to_named_configured_km", 1e9) < 50
        c.add("named_location_is_the_nearest_configured_location", "pass" if agree else "fail",
              f"named {named}, nearest {nearest}, {ident.get('distance_to_named_configured_km')} km from the configured point")
    else:
        c.add("location_can_be_identified", "warn", "no location in the file name; coordinates would be matched to the nearest configured point")

    # ---- value sanity
    for v, s in series.items():
        vals = np.array([float(x) for k, x in s.items() if k[4:] != "13" and x is not None and float(x) != fill])
        lim = checks.LIMITS.get(v)
        n_out = int(((vals < lim[0]) | (vals > lim[1])).sum()) if lim and len(vals) else 0
        coverage[v].update(min=float(vals.min()) if len(vals) else None, max=float(vals.max()) if len(vals) else None,
                           mean=float(vals.mean()) if len(vals) else None, n_outside_qc_limits=n_out)
        c.add(f"values_within_physical_limits_{v}", "fail" if n_out else "pass", f"{n_out} outside {lim}" if n_out else "")

    # ---- interpretation evidence
    sem = {}
    for v, s in series.items():
        stat = config.VARIABLE_SEMANTICS.get(v, ("unknown", "unknown"))[1]
        ac = annual_consistency(s, fill)
        if "maximum_of_hourly" in stat:
            kind, ok_ = "extreme_max", (ac["max_abs_diff_max"] is not None and ac["max_abs_diff_max"] <= EXTREME_TOL)
        elif "minimum_of_hourly" in stat:
            kind, ok_ = "extreme_min", (ac["max_abs_diff_min"] is not None and ac["max_abs_diff_min"] <= EXTREME_TOL)
        else:
            kind, ok_ = "mean", (ac["max_abs_diff_weighted"] is not None and ac["max_abs_diff_weighted"] <= ROUNDING_TOL)
        ac.update(documented_statistic=stat, test=kind, annual_value_consistent_with_documented_statistic=bool(ok_),
                  annual_also_consistent_with_simple_mean=bool(ac["max_abs_diff_simple"] is not None and ac["max_abs_diff_simple"] <= ROUNDING_TOL))
        sem[v] = ac
        c.add(f"annual_value_consistent_with_{v}_definition", "pass" if ok_ else "warn",
              f"{kind}: max |annual - aggregate| = {ac['max_abs_diff_weighted'] if kind == 'mean' else ac['max_abs_diff_max' if kind == 'extreme_max' else 'max_abs_diff_min']}")
    if {"T2M", "T2M_MAX", "T2M_MIN"} <= set(series):
        keys = [k for k in series["T2M"] if k[4:] != "13"]
        trip = [(series["T2M_MAX"][k], series["T2M"][k], series["T2M_MIN"][k]) for k in keys
                if all(series[x].get(k) is not None and float(series[x][k]) != fill for x in ("T2M_MAX", "T2M", "T2M_MIN"))]
        bad = sum(1 for hi, mid, lo in trip if not (hi >= mid >= lo))
        sem["ordering_Tmax_ge_T_ge_Tmin"] = {"months_checked": len(trip), "violations": bad}
        c.add("T2M_MAX_ge_T2M_ge_T2M_MIN_every_month", "fail" if bad else "pass", f"{bad} violations in {len(trip)} months")
    res["semantics_evidence"] = sem
    res["checks"] = list(c)
    res["status"] = "fail" if any(x["status"] == "fail" for x in c) else ("warn" if any(x["status"] == "warn" for x in c) else "pass")
    res["counts"] = {s: sum(1 for x in c if x["status"] == s) for s in ("pass", "info", "warn", "fail")}
    return res


def compare_files(docs):
    """docs: {name: parsed JSON}. Cross-file consistency."""
    out, names = {}, list(docs)
    base = docs[names[0]]

    def same(getter, norm=lambda x: x):
        return all(json.dumps(norm(getter(d)), sort_keys=True) == json.dumps(norm(getter(base)), sort_keys=True) for d in docs.values())
    hdr_nosrc = lambda d: {k: v for k, v in (d.get("header") or {}).items() if k != "sources"}
    out["header_identical_except_sources"] = same(hdr_nosrc)
    out["header_sources_identical_as_sets"] = same(lambda d: sorted((d.get("header") or {}).get("sources", [])))
    out["header_sources_identical_in_order"] = same(lambda d: (d.get("header") or {}).get("sources", []))
    out["parameters_metadata_identical"] = same(lambda d: d.get("parameters"))
    out["parameter_sets_identical"] = same(lambda d: sorted(d["properties"]["parameter"]))
    out["monthly_key_sets_identical"] = same(lambda d: sorted(next(iter(d["properties"]["parameter"].values()))))
    out["api_version"] = sorted({str((d.get("header") or {}).get("api", {}).get("version")) for d in docs.values()})
    out["time_standard"] = sorted({str((d.get("header") or {}).get("time_standard")) for d in docs.values()})
    out["title"] = sorted({str((d.get("header") or {}).get("title")) for d in docs.values()})
    pts = {n: tuple(d["geometry"]["coordinates"][:2]) for n, d in docs.items()}
    out["coordinates_all_distinct"] = len(set(pts.values())) == len(pts)
    out["min_pairwise_distance_km"] = round(min(haversine_km(pts[a][1], pts[a][0], pts[b][1], pts[b][0])
                                                for i, a in enumerate(names) for b in names[i + 1:]), 1) if len(names) > 1 else None
    ident = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for v in docs[a]["properties"]["parameter"]:
                if v in docs[b]["properties"]["parameter"]:
                    sa, sb = docs[a]["properties"]["parameter"][v], docs[b]["properties"]["parameter"][v]
                    ks = [k for k in sa if k in sb and k[4:] != "13" and float(sa[k]) != -999]
                    same_n = sum(1 for k in ks if sa[k] == sb[k])
                    if ks and same_n / len(ks) > 0.5:
                        ident.append({"pair": [a, b], "variable": v, "share_identical_values": round(same_n / len(ks), 3)})
    out["pairs_with_mostly_identical_series"] = ident
    return out
