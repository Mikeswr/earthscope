"""Run retrospective compound hot-dry analysis on downloaded Ghana regional grids."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the repository root importable as the earthscope package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import requests

from earthscope import config
from spatial.analysis import filter_cells_to_boundary
from spatial.compound import compound_hot_dry_analysis
from spatial.compound_summary import write_compound_summaries
from spatial.validation import validate_regional_frame


def load_ghana_adm0_boundary(output_dir):
    """Retrieve and preserve the geoBoundaries open Ghana ADM0 geometry and metadata."""
    metadata_url = "https://www.geoboundaries.org/api/current/gbOpen/GHA/ADM0/"
    response = requests.get(metadata_url, timeout=30)
    response.raise_for_status()
    metadata = response.json()
    if isinstance(metadata, list):
        if not metadata:
            raise ValueError("geoBoundaries returned an empty Ghana ADM0 metadata response.")
        metadata = metadata[0]
    if not isinstance(metadata, dict):
        raise ValueError("geoBoundaries ADM0 metadata was not a JSON object.")

    download_url = metadata.get("simplifiedGeometryGeoJSON") or metadata.get("gjDownloadURL")
    if not download_url:
        raise ValueError("geoBoundaries did not provide a Ghana ADM0 GeoJSON URL.")
    download_url = download_url.replace(
        "https://github.com/wmgeolab/geoBoundaries/raw/",
        "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/",
    ).replace(
        "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/",
        "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/",
    )
    geo_response = requests.get(download_url, timeout=90)
    geo_response.raise_for_status()
    geojson = geo_response.json()
    if geojson.get("type") != "FeatureCollection" or not geojson.get("features"):
        raise ValueError("Ghana ADM0 download was not a valid GeoJSON FeatureCollection.")

    boundary_path = output_dir / "ghana_adm0_boundary.geojson"
    boundary_bytes = (json.dumps(geojson, separators=(",", ":")) + "\n").encode("utf-8")
    boundary_path.write_bytes(boundary_bytes)
    boundary_meta = {
        "provider": "geoBoundaries",
        "api_metadata_url": metadata_url,
        "download_url": download_url,
        "boundary_type": metadata.get("boundaryType"),
        "boundary_year_represented": metadata.get("boundaryYearRepresented"),
        "license": metadata.get("license"),
        "geojson_file": boundary_path.name,
        "geojson_sha256": hashlib.sha256(boundary_bytes).hexdigest(),
    }
    return geojson, boundary_meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=str(config.data_dir() / "spatial" / "nasa_power"))
    parser.add_argument("--output-dir", default="reports/compound_hot_dry")
    parser.add_argument("--start", type=int, default=1981)
    parser.add_argument("--end", type=int, default=config.latest_complete_year())
    parser.add_argument("--minimum-cell-coverage", type=float, default=0.80)
    parser.add_argument("--baseline-start", type=int, default=1991)
    parser.add_argument("--baseline-end", type=int, default=2020)
    parser.add_argument("--boundary-file", default=None)
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir = Path(args.input_dir)
    frames = {}
    validation = {}
    for variable in ("T2M", "PRECTOTCORR"):
        path = input_dir / f"ghana_power_regional_{variable}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing required regional input: {path}")
        frame = pd.read_csv(path, parse_dates=["date"])
        report = validate_regional_frame(
            frame, variable, args.start, args.end, args.minimum_cell_coverage
        )
        validation[variable] = report
        if not report["analysis_eligible"]:
            raise ValueError(
                f"{variable} dataset failed pre-analysis quality control: "
                + "; ".join(report["errors"] + report["warnings"])
            )
        frames[variable] = frame

    if args.boundary_file:
        boundary_path = Path(args.boundary_file)
        geojson = json.loads(boundary_path.read_text(encoding="utf-8"))
        boundary_meta = {
            "provider": "user-supplied",
            "geojson_file": str(boundary_path),
            "geojson_sha256": hashlib.sha256(boundary_path.read_bytes()).hexdigest(),
        }
    else:
        geojson, boundary_meta = load_ghana_adm0_boundary(output_dir)

    for variable in frames:
        before = int(frames[variable]["cell_id"].nunique())
        frames[variable] = filter_cells_to_boundary(frames[variable], geojson)
        after = int(frames[variable]["cell_id"].nunique())
        validation[variable]["cells_before_boundary_filter"] = before
        validation[variable]["cells_after_boundary_filter"] = after
        if after == 0:
            raise ValueError(f"No {variable} grid-cell centres fell inside Ghana ADM0.")

    monthly, annual, trends, analysis_meta, diagnostics = compound_hot_dry_analysis(
        frames["T2M"],
        frames["PRECTOTCORR"],
        args.start,
        args.end,
        baseline=(args.baseline_start, args.baseline_end),
    )
    monthly_path = output_dir / "compound_hot_dry_monthly.csv"
    annual_path = output_dir / "compound_hot_dry_annual_frequency.csv"
    trends_path = output_dir / "compound_hot_dry_cell_trends.csv"
    monthly.to_csv(monthly_path, index=False)
    annual.to_csv(annual_path, index=False)
    trends.to_csv(trends_path, index=False)
    summary_outputs = write_compound_summaries(annual, trends, output_dir)

    file_hashes = {}
    for variable in ("T2M", "PRECTOTCORR"):
        source_path = input_dir / f"ghana_power_regional_{variable}.csv"
        file_hashes[source_path.name] = hashlib.sha256(source_path.read_bytes()).hexdigest()

    run_metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "code_repository": "https://github.com/Mikeswr/earthscope",
        "source": "NASA POWER Monthly Regional API",
        "input_file_sha256": file_hashes,
        "pre_analysis_qc": validation,
        "boundary": boundary_meta,
        "analysis": analysis_meta,
        "outputs": {
            "monthly": {"file": monthly_path.name, "rows": len(monthly)},
            "annual": {"file": annual_path.name, "rows": len(annual)},
            "cell_trends": {"file": trends_path.name, "rows": len(trends)},
            **summary_outputs,
        },
        "software": {
            "python": __import__("platform").python_version(),
            "pandas": pd.__version__,
        },
    }
    metadata_path = output_dir / "analysis_run.json"
    metadata_path.write_text(json.dumps(run_metadata, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Monthly rows: {len(monthly):,}")
    print(f"Annual cell-years: {len(annual):,}")
    print(f"Ghana grid cells analysed: {len(trends):,}")
    print(f"Cells with at least one compound event: "
          f"{int((annual.groupby('cell_id')['n_hot_dry_months'].sum() > 0).sum()):,}")
    print(f"Run metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
