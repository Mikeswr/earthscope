"""Fetch NASA POWER monthly data for configured Ghana locations (needs internet access)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import datetime as dt
import json
import time

import requests

from earthscope import config
from earthscope.ingest import pipeline, power


def fetch_one(url, retries=3, timeout=90, sleep=None):
    """GET with retry on timeouts, 429 and 5xx. Raises on final failure. Never returns fake data."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code}")
            elif r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            else:
                return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
        if attempt < retries:
            (sleep or time.sleep)(2 ** attempt)
    raise RuntimeError(f"Failed after {retries} attempts: {last}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locations", nargs="*", help="names from locations.yaml (default: all)")
    ap.add_argument("--locations-file", help="alternative YAML file of locations")
    ap.add_argument("--add", nargs="*", default=[], metavar="NAME:LAT:LON", help="extra custom locations")
    ap.add_argument("--start", type=int, default=config.POWER_START_YEAR)
    ap.add_argument("--end", type=int, default=config.latest_complete_year())
    ap.add_argument("--params", nargs="*", default=config.POWER_PARAMS)
    ap.add_argument("--format", choices=["JSON", "CSV"], default="JSON")
    ap.add_argument("--print-urls", action="store_true", help="only print request URLs and exit")
    args = ap.parse_args(argv)

    locs = config.load_locations(args.locations_file)
    for item in args.add:
        n, la, lo = item.split(":")
        locs[n] = (float(la), float(lo))
    names = args.locations or list(locs)
    unknown = [n for n in names if n not in locs]
    if unknown:
        print(f"Unknown locations: {unknown}. Known: {list(locs)}")
        return 2

    if args.print_urls:
        for n in names:
            print(f"{n}: {power.build_url(*locs[n], args.start, args.end, args.params, args.format)}")
        return 0

    failed = []
    for n in names:
        lat, lon = locs[n]
        url = power.build_url(lat, lon, args.start, args.end, args.params, args.format)
        try:
            r = fetch_one(url)
            text = r.text
            # structural check only: garbage is never stored as data, but a valid response is kept
            # even if its unit metadata needs inspection (that is checked when processing)
            power.validate_structure(text, args.format)
        except Exception as e:
            print(f"[FAIL] {n}: {e}")
            failed.append(n)
            continue
        dest = config.raw_dir() / pipeline.canonical_name(n, args.start, args.end, args.format)
        dest.write_text(text, encoding="utf-8")
        (dest.parent / (dest.name + pipeline.FETCH_SUFFIX)).write_text(json.dumps({
            "request_url": url, "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "http_status": r.status_code,
            "requested": {"location": n, "latitude": lat, "longitude": lon, "start": args.start, "end": args.end,
                          "parameters": args.params, "community": config.POWER_COMMUNITY, "format": args.format}},
            indent=2))
        print(f"[OK]   {n}: saved {dest}")

    if len(failed) < len(names):
        try:
            df = pipeline.build_processed(locations=locs)
        except Exception as e:
            print(f"[FAIL] raw files were saved but processing was refused: {e}")
            return 3
        print(f"Processed {len(df)} rows -> {config.processed_dir() / pipeline.PROCESSED_NAME}")
    if failed:
        print(f"Incomplete: {len(failed)} location(s) failed: {failed}. No data was substituted.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
