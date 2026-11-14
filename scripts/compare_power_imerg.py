"""Run the matched-support NASA POWER vs GPM IMERG precipitation comparison."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from spatial.imerg_validation import (
    DEFAULT_END,
    DEFAULT_START,
    compare_power_imerg,
    write_imerg_comparison,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--power-csv",
        default="data/spatial/nasa_power/ghana_power_regional_PRECTOTCORR.csv",
    )
    parser.add_argument(
        "--imerg-csv",
        default="data/spatial/imerg/earthscope_ghana_imerg_monthly_power_support_1998_2025_09.csv",
    )
    parser.add_argument(
        "--grid-csv",
        default="data/reference/ghana_power_grid_cells_2007_adm0.csv",
    )
    parser.add_argument("--output-dir", default="reports/imerg_validation")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--minimum-cell-coverage", type=float, default=0.80)
    args = parser.parse_args(argv)

    for label, value in [
        ("POWER CSV", args.power_csv),
        ("IMERG CSV", args.imerg_csv),
        ("POWER grid reference", args.grid_csv),
    ]:
        if not Path(value).exists():
            parser.error(f"{label} not found: {value}")

    power = pd.read_csv(args.power_csv)
    imerg = pd.read_csv(args.imerg_csv)
    grid = pd.read_csv(args.grid_csv)
    result = compare_power_imerg(
        power,
        imerg,
        grid,
        start=args.start,
        end=args.end,
        minimum_cell_coverage=args.minimum_cell_coverage,
    )
    written = write_imerg_comparison(result, args.output_dir)
    print(json.dumps({
        "analysis_eligible": result["metadata"]["analysis_eligible"],
        "period": result["metadata"]["period"],
        "overall": result["metadata"]["overall"],
        "outputs": written,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
