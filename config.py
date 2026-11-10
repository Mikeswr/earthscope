import datetime
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

GHANA_BBOX = (-3.26, 4.74, 1.20, 11.17)  # west, south, east, north

POWER_BASE = "https://power.larc.nasa.gov/api/temporal"
POWER_COMMUNITY = "AG"
POWER_PARAMS = ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS10M", "ALLSKY_SFC_SW_DWN"]
POWER_START_YEAR = 1981

# Units this project EXPECTS. They are compared with the units stated in each NASA response.
# They are never silently applied: a response without units is rejected unless the user passes
# --assume-documented-units, and the table then records unit_source = assumed_documented_default.
EXPECTED_UNITS = {
    "T2M": "C", "T2M_MAX": "C", "T2M_MIN": "C",
    "PRECTOTCORR": "mm/day", "RH2M": "%", "WS10M": "m/s",
    "ALLSKY_SFC_SW_DWN": "kW-hr/m^2/day",
}

# Spellings accepted for the same unit. Anything else (for example K) is rejected, not converted.
UNIT_ALIASES = {
    "c": "C", "\u00b0c": "C", "degc": "C", "deg c": "C", "degrees c": "C", "celsius": "C",
    "mm/day": "mm/day", "mm/d": "mm/day", "mm day-1": "mm/day", "mm day^-1": "mm/day", "mm/day ": "mm/day",
    "%": "%", "percent": "%",
    "m/s": "m/s", "m s-1": "m/s", "m s^-1": "m/s", "meters/second": "m/s", "m/sec": "m/s",
    "kw-hr/m^2/day": "kW-hr/m^2/day", "kwh/m^2/day": "kW-hr/m^2/day", "kw-hr/m2/day": "kW-hr/m^2/day",
}

# What each variable represents in the POWER MONTHLY product.
# Source: the NASA POWER data processing page (nested hierarchy: hourly values -> daily mean/max/min
# -> monthly mean of the days -> annual mean). Maximum and minimum parameters such as T2M_MAX are the
# stated exception: they "retain the value from the original instantaneous hourly time" through the
# hierarchy, so the monthly T2M_MAX is the highest hourly value in the month and the annual value is
# the highest of the year. The average of the daily maximum is a different parameter (T2M_MAX_AVG).
# Checked against the five real files: annual T2M_MAX equals max(12 monthly values) and annual T2M_MIN
# equals min(12 monthly values) in 45 of 45 years at all five locations; annual values of the mean
# parameters equal the day-weighted mean of the months to within rounding (0.005).
SEMANTICS_STATUS = "nasa_documented_and_consistent_with_returned_data"
VARIABLE_SEMANTICS = {
    "T2M": ("air_temperature_2m", "monthly_mean_of_daily_mean"),
    "T2M_MAX": ("air_temperature_2m", "monthly_maximum_of_hourly_values"),
    "T2M_MIN": ("air_temperature_2m", "monthly_minimum_of_hourly_values"),
    "PRECTOTCORR": ("precipitation", "monthly_mean_of_daily_precipitation_rate_not_a_monthly_total"),
    "RH2M": ("relative_humidity_2m", "monthly_mean_of_daily_mean"),
    "WS10M": ("wind_speed_10m", "monthly_mean_of_daily_mean"),
    "ALLSKY_SFC_SW_DWN": ("all_sky_surface_shortwave_downward_irradiance", "monthly_mean_of_daily_total"),
}

# How the annual value for the trend analysis is built from the 12 monthly values.
# Extremes use the annual extreme (as NASA's own annual column does); the others use the day-weighted mean.
ANNUAL_AGGREGATION = {"T2M_MAX": "max", "T2M_MIN": "min"}


def annual_how(variable):
    return ANNUAL_AGGREGATION.get(variable, "day_weighted_mean")


# Multiple-testing families. FDR is applied within each family.
# The solar variable blends several satellite and model sources over time, so it is kept apart from the
# six meteorological variables rather than mixed into one family.
FDR_FAMILIES = {"ALLSKY_SFC_SW_DWN": "secondary_solar"}
PRIMARY_FAMILY = "primary"

# Environment variable names for credentials (see docs/CREDENTIALS.md)
ENV_OPENWEATHER = "OPENWEATHER_API_KEY"
ENV_AGROMONITORING = "AGROMONITORING_API_KEY"

VARIABLE_LABELS = {
    "T2M": "Mean air temperature at 2 m",
    "T2M_MAX": "Maximum air temperature at 2 m",
    "T2M_MIN": "Minimum air temperature at 2 m",
    "PRECTOTCORR": "Precipitation (bias corrected)",
    "RH2M": "Relative humidity at 2 m",
    "WS10M": "Wind speed at 10 m",
    "ALLSKY_SFC_SW_DWN": "All sky surface shortwave downward irradiance",
}



def data_dir():
    return Path(os.environ.get("EARTHSCOPE_DATA_DIR", ROOT / "data"))


def raw_dir():
    p = data_dir() / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def processed_dir():
    p = data_dir() / "processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def latest_complete_year():
    return datetime.date.today().year - 1


def load_locations(path=None):
    path = Path(path) if path else ROOT / "locations.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f)
    return {name: (float(v["lat"]), float(v["lon"])) for name, v in raw.items()}


def get_key(name):
    """Credential lookup: environment, Streamlit Cloud secrets, then local secrets file."""
    value = os.environ.get(name)
    if value:
        return value
    # Streamlit Community Cloud exposes configured secrets through st.secrets.
    # Import lazily so command-line ingestion does not require an active Streamlit runtime.
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.exists():
        import tomllib
        with open(secrets, "rb") as f:
            value = tomllib.load(f).get(name)
        return value or None
    return None
