"""Probe the keyed APIs and report REAL status per endpoint. Run it where internet access exists.

    python scripts/check_apis.py [--create-polygon] [--save-samples]

Reads OPENWEATHER_API_KEY and AGROMONITORING_API_KEY (environment or .streamlit/secrets.toml).
Writes data/processed/api_probe_report.json. The report never contains a key. An endpoint counts
as working only if it returned HTTP 200 AND the response had the shape the parser expects.
HTTP 403 means the key is valid but the endpoint is not in your plan; 401 means the key was rejected.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import datetime as dt
import json

from earthscope import config
from earthscope.ingest import agromonitoring as agro
from earthscope.ingest import http, openweather as owm

ACCRA = (5.60, -0.19)


def shape_of(x):
    if isinstance(x, list):
        return {"type": "list", "length": len(x), "first_entry_keys": sorted(x[0])[:12] if x and isinstance(x[0], dict) else None}
    if isinstance(x, dict):
        return {"type": "object", "keys": sorted(x)[:20]}
    return {"type": type(x).__name__}


def run_probes(create_polygon=False, samples_dir=None, lat=ACCRA[0], lon=ACCRA[1]):
    day = "2020-01-15"
    t0 = int(dt.datetime(2020, 1, 15, tzinfo=dt.timezone.utc).timestamp())
    a0 = int(dt.datetime(2024, 1, 15, tzinfo=dt.timezone.utc).timestamp())
    results = []

    def probe(service, name, fn, check):
        entry = {"service": service, "endpoint": name}
        try:
            data = fn()
            entry.update(http_status=200, shape=shape_of(data))
            try:
                check(data)
                entry["parser_check"] = "passed"
                entry["usable"] = True
            except Exception as e:
                entry["parser_check"] = f"FAILED: {http.redact(e)}"
                entry["usable"] = False
            if samples_dir:
                Path(samples_dir).mkdir(parents=True, exist_ok=True)
                (Path(samples_dir) / f"{service}_{name}.json").write_text(json.dumps(data, indent=1)[:200000])
        except http.ApiError as e:
            entry.update(http_status=e.status, error=str(e), hint=e.hint, usable=False)
        except Exception as e:
            entry.update(http_status=None, error=http.redact(f"{type(e).__name__}: {e}"), usable=False)
        results.append(entry)
        return entry

    ow_ok = config.get_key(config.ENV_OPENWEATHER) is not None
    ag_ok = config.get_key(config.ENV_AGROMONITORING) is not None
    probe("openweather", "current_weather_2.5", lambda: owm.current_weather(lat, lon), lambda d: d["main"]["temp"])
    probe("openweather", "onecall_3.0_day_summary", lambda: owm.day_summary(lat, lon, day),
          lambda d: owm.parse_day_summary(d, "Accra", lat, lon).shape[0] > 0 or (_ for _ in ()).throw(ValueError("no rows")))
    probe("openweather", "history_hourly", lambda: owm.history_hourly(lat, lon, t0, t0 + 3 * 3600),
          lambda d: owm.parse_history_hourly(d, "Accra", lat, lon).shape[0] > 0 or (_ for _ in ()).throw(ValueError("no rows")))
    probe("agromonitoring", "current_weather", lambda: agro.current_weather(lat, lon), lambda d: d["main"])
    probe("agromonitoring", "weather_history", lambda: agro.weather_history(lat, lon, a0, a0 + 86400),
          lambda d: agro.parse_weather_history(d, "Accra", lat, lon).shape[0] > 0 or (_ for _ in ()).throw(ValueError("no rows")))
    polys = probe("agromonitoring", "list_polygons", agro.list_polygons, lambda d: isinstance(d, list) or (_ for _ in ()).throw(ValueError("not a list")))
    poly_id = None
    if polys.get("usable"):
        existing = agro.list_polygons()
        if existing:
            poly_id = existing[0]["id"]
        elif create_polygon:
            e = probe("agromonitoring", "create_polygon", lambda: agro.create_polygon("EarthScope probe", agro.square_polygon(lat, lon)),
                      lambda d: d["id"])
            poly_id = next((r.get("id") for r in [e] if r.get("usable")), None)
            if e.get("usable"):
                poly_id = agro.list_polygons()[-1]["id"]
    if poly_id:
        probe("agromonitoring", "ndvi_history", lambda: agro.ndvi_history(poly_id, a0, a0 + 365 * 86400),
              lambda d: agro.parse_ndvi_history(d, poly_id, "probe", lat, lon).shape[0] >= 0)
    else:
        results.append({"service": "agromonitoring", "endpoint": "ndvi_history", "usable": False,
                        "skipped": "needs a polygon; rerun with --create-polygon or create one in the Agro dashboard"})
    return {"run_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "keys_present": {"openweather": ow_ok, "agromonitoring": ag_ok}, "results": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--create-polygon", action="store_true", help="create a ~25 ha test polygon if the account has none")
    ap.add_argument("--save-samples", action="store_true", help="save raw responses to data/raw/api_samples (gitignored)")
    args = ap.parse_args(argv)
    samples = config.raw_dir() / "api_samples" if args.save_samples else None
    report = run_probes(args.create_polygon, samples)
    out = config.processed_dir() / "api_probe_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"keys present: {report['keys_present']}")
    for r in report["results"]:
        mark = "OK  " if r.get("usable") else "FAIL"
        extra = r.get("hint") or r.get("skipped") or r.get("parser_check", "")
        print(f"[{mark}] {r['service']:15s} {r['endpoint']:26s} status={r.get('http_status')}  {extra}")
    print(f"\nreport written to {out} (contains no keys). Integration counts as working only for rows marked OK.")
    return 0 if all(r.get("usable") for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
