"""Download Ghana-wide NASA POWER regional monthly grids.

Usage:
    python -m scripts.fetch_power_regional --start 1981 --end 2025
    python -m scripts.fetch_power_regional --variables T2M,PRECTOTCORR --start 2001 --end 2025

Each variable is saved separately because NASA POWER regional parameters can have
different native spatial resolutions. No interpolation or resampling is performed.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from spatial.power_regional import fetch_parameter, estimate_grid_spacing
from earthscope import config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Fetch NASA POWER Ghana regional monthly grid data.")
    parser.add_argument("--variables", default=",".join(config.POWER_PARAMS),
                        help="Comma-separated NASA POWER parameter codes.")
    parser.add_argument("--start", type=int, default=config.POWER_START_YEAR)
    parser.add_argument("--end", type=int, default=config.latest_complete_year())
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    variables = [v.strip().upper() for v in args.variables.split(",") if v.strip()]
    unknown = sorted(set(variables) - set(config.POWER_PARAMS))
    if unknown:
        print(f"Unsupported variables: {', '.join(unknown)}")
        return 2
    if args.start > args.end:
        print("Start year must not be later than end year.")
        return 2

    output_dir = Path(args.output_dir) if args.output_dir else config.data_dir() / "spatial" / "nasa_power"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "source": "NASA POWER regional monthly API",
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "geographic_bbox_west_south_east_north": list(config.GHANA_BBOX),
        "requested_start_year": args.start,
        "requested_end_year": args.end,
        "method": "native regional grid cells; no interpolation or resampling",
        "variables": {},
    }

    failures = []
    for variable in variables:
        print(f"Fetching {variable}...")
        try:
            frame = fetch_parameter(variable, args.start, args.end)
            csv_path = output_dir / f"ghana_power_regional_{variable}.csv"
            frame.to_csv(csv_path, index=False)
            records = frame.attrs.get("fetch_records", [])
            variable_meta = {
                "file": csv_path.name,
                "rows": int(len(frame)),
                "unique_cells": int(frame["cell_id"].nunique()),
                "first_valid_year": int(frame.loc[frame.value.notna(), "date"].dt.year.min())
                    if frame.value.notna().any() else None,
                "last_valid_year": int(frame.loc[frame.value.notna(), "date"].dt.year.max())
                    if frame.value.notna().any() else None,
                "unit": sorted(frame["unit"].dropna().astype(str).unique().tolist()),
                "unit_source": sorted(frame["unit_source"].dropna().astype(str).unique().tolist()),
                "grid_spacing": estimate_grid_spacing(frame),
                "request_count": len(records),
                "requests": records,
            }
            summary["variables"][variable] = variable_meta
            print(f"  Saved {len(frame):,} rows across {variable_meta['unique_cells']:,} cells.")
        except Exception as exc:
            failures.append((variable, str(exc)))
            print(f"  FAILED: {exc}")

    summary["failed_variables"] = [{"variable": v, "error": e} for v, e in failures]
    metadata_path = output_dir / "fetch_metadata.json"
    metadata_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Metadata: {metadata_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
