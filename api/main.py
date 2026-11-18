"""Read-only FastAPI interface for the EarthScope scientific outputs.

Run from the repository root:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# The project configuration lives in the repository-root config.py module.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402

API_VERSION = "1.0.0"
PROCESSED_DIR = config.data_dir() / "processed"
TRENDS_FILE = PROCESSED_DIR / "trend_results.csv"
METADATA_FILE = PROCESSED_DIR / "power_monthly_metadata.json"

VARIABLE_DESCRIPTIONS = {
    "T2M": "Mean air temperature at 2 metres",
    "T2M_MAX": "Maximum air temperature at 2 metres",
    "T2M_MIN": "Minimum air temperature at 2 metres",
    "PRECTOTCORR": "Bias-corrected precipitation rate",
    "RH2M": "Relative humidity at 2 metres",
    "WS10M": "Wind speed at 10 metres",
    "ALLSKY_SFC_SW_DWN": "All-sky surface shortwave downward irradiance",
}

VARIABLE_UNITS = {
    "T2M": "C",
    "T2M_MAX": "C",
    "T2M_MIN": "C",
    "PRECTOTCORR": "mm/day",
    "RH2M": "%",
    "WS10M": "m/s",
    "ALLSKY_SFC_SW_DWN": "kW-hr/m^2/day",
}

app = FastAPI(
    title="EarthScope API",
    description=(
        "Read-only API for location metadata and processed NASA POWER climate "
        "trend results. NASA POWER values are gridded estimates, not station observations."
    ),
    version=API_VERSION,
)

allowed_origins = [
    origin.strip()
    for origin in __import__("os").environ.get(
        "LUMOSX_ALLOWED_ORIGINS",
        "https://lumosx-seven.vercel.app,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _locations() -> dict[str, tuple[float, float]]:
    try:
        return config.load_locations()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Location configuration could not be loaded.") from exc


@lru_cache(maxsize=1)
def _trend_records() -> tuple[list[dict[str, Any]], list[str]]:
    if not TRENDS_FILE.is_file():
        raise FileNotFoundError("Processed trend results are not available.")
    frame = pd.read_csv(TRENDS_FILE)
    columns = list(frame.columns)
    # Replace pandas NaN/NaT values with JSON-safe nulls.
    records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
    return records, columns


def _metadata() -> dict[str, Any]:
    if not METADATA_FILE.is_file():
        raise FileNotFoundError("Processed dataset metadata are not available.")
    return json.loads(METADATA_FILE.read_text(encoding="utf-8"))


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "earthscope-api",
        "version": API_VERSION,
        "processed_data_available": TRENDS_FILE.is_file(),
        "metadata_available": METADATA_FILE.is_file(),
    }


@app.get("/api/v1/locations", tags=["catalogue"])
def locations() -> dict[str, Any]:
    configured = _locations()
    return {
        "count": len(configured),
        "locations": [
            {"name": name, "latitude": lat, "longitude": lon}
            for name, (lat, lon) in configured.items()
        ],
    }


@app.get("/api/v1/variables", tags=["catalogue"])
def variables() -> dict[str, Any]:
    items = [
        {
            "code": code,
            "label": config.VARIABLE_LABELS.get(code, VARIABLE_DESCRIPTIONS[code]),
            "description": VARIABLE_DESCRIPTIONS[code],
            "unit": VARIABLE_UNITS[code],
            "source": "NASA POWER",
            "temporal_resolution": "monthly",
            "data_kind": "gridded_estimate_not_station_observation",
        }
        for code in config.POWER_PARAMS
        if code in VARIABLE_DESCRIPTIONS
    ]
    return {"count": len(items), "variables": items}


@app.get("/api/v1/metadata", tags=["data"])
def metadata() -> dict[str, Any]:
    try:
        data = _metadata()
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Processed dataset metadata are unavailable.") from exc
    return {
        "source": "NASA POWER",
        "data_kind": "gridded_estimate_not_station_observation",
        "temporal_resolution": "monthly",
        "metadata": data,
    }


@app.get("/api/v1/trends", tags=["analysis"])
def trends(
    location: str | None = Query(default=None, description="Configured location name"),
    variable: str | None = Query(default=None, description="NASA POWER variable code"),
    significant_only: bool = Query(default=False, description="Keep only FDR-significant results"),
) -> dict[str, Any]:
    configured_locations = _locations()
    valid_variables = set(config.POWER_PARAMS)

    if location is not None and location not in configured_locations:
        raise HTTPException(status_code=422, detail=f"Unknown location. Choose from: {', '.join(configured_locations)}")
    if variable is not None and variable not in valid_variables:
        raise HTTPException(status_code=422, detail=f"Unknown variable. Choose from: {', '.join(config.POWER_PARAMS)}")

    try:
        records, columns = _trend_records()
    except (OSError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=503, detail="Processed trend results are unavailable.") from exc

    selected = records
    if location is not None:
        selected = [row for row in selected if row.get("location") == location]
    if variable is not None:
        selected = [row for row in selected if row.get("variable") == variable]
    if significant_only:
        selected = [row for row in selected if row.get("significant_fdr") in (True, 1, "True", "true")]

    return {
        "count": len(selected),
        "filters": {
            "location": location,
            "variable": variable,
            "significant_only": significant_only,
        },
        "source": "NASA POWER",
        "data_kind": "gridded_estimate_not_station_observation",
        "method": "Mann-Kendall with AR1 effective-sample-size correction; Sen's slope per decade; Benjamini-Hochberg FDR",
        "columns": columns,
        "results": selected,
    }
