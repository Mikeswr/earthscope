"""Validate downloaded NASA POWER regional grid CSVs before spatial analysis.

Usage:
    python -m scripts.validate_regional_grid [--input-dir data/spatial/nasa_power]
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from earthscope import config
from spatial.validation import validate_regional_frame


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        default=str(config.data_dir() / "spatial" / "nasa_power"),
    )
    parser.add_argument("--start", type=int, default=config.POWER_START_YEAR)
    parser.add_argument("--end", type=int, default=config.latest_complete_year())
    parser.add_argument("--minimum-cell-coverage", type=float, default=0.80)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    folder = Path(args.input_dir)
    reports = {}
    failures = []
    for variable in config.POWER_PARAMS:
        path = folder / f"ghana_power_regional_{variable}.csv"
        if not path.exists():
            reports[variable] = {
                "status": "not_available",
                "analysis_eligible": False,
                "errors": [f"File not found: {path}"],
                "warnings": [],
            }
            failures.append(variable)
            continue
        frame = pd.read_csv(path, parse_dates=["date"])
        report = validate_regional_frame(
            frame, variable, args.start, args.end, args.minimum_cell_coverage
        )
        reports[variable] = report
        if not report["analysis_eligible"]:
            failures.append(variable)
        print(
            f"{report['status'].upper():5s} {variable}: "
            f"{report['cells']} cells, {report['valid_observations']:,} valid months, "
            f"minimum cell coverage={report['minimum_cell_valid_fraction']}"
        )
        for message in report["errors"]:
            print(f"  ERROR: {message}")
        for message in report["warnings"]:
            print(f"  WARN: {message}")

    output = Path(args.output) if args.output else folder / "regional_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "source": "NASA POWER regional monthly API",
        "requested_start_year": args.start,
        "requested_end_year": args.end,
        "minimum_cell_coverage": args.minimum_cell_coverage,
        "variables": reports,
        "analysis_ready": not failures,
        "ineligible_variables": failures,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nValidation report: {output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
