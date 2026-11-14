"""Compound hot-dry conditions from monthly gridded climate data.

Inputs:
- Monthly mean 2 m air temperature (NASA POWER T2M, degrees C).
- Monthly mean daily precipitation rate (NASA POWER PRECTOTCORR, mm/day).

Definitions:
- Heat anomaly: calendar-month T2M z-score relative to a fixed baseline.
- SPI-3: gamma-distribution standardisation of trailing three-month
  precipitation accumulation, fitted separately for each ending calendar month.
- Compound hot-dry month: heat z-score >= threshold AND SPI-3 <= threshold.

This is a retrospective compound climate-stress indicator. It is not a heatwave
definition, an impact model, a soil-moisture drought index, or an operational
early-warning forecast.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import gamma, norm

from earthscope.trends import engine

REQUIRED_COLUMNS = {
    "date", "variable", "value", "latitude", "longitude", "cell_id", "unit",
}
DEFAULT_BASE_PERIOD = (1991, 2020)
DEFAULT_HEAT_Z_THRESHOLD = 1.0
DEFAULT_SPI3_THRESHOLD = -1.0
DEFAULT_MIN_BASE_YEARS = 20
DEFAULT_MIN_VALID_MONTHS_PER_YEAR = 9


def _prepare_cells(frame, variable, start_year, end_year):
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{variable} input is missing columns: {', '.join(sorted(missing))}")
    d = frame.loc[frame["variable"] == variable].copy()
    if d.empty:
        raise ValueError(f"No {variable} rows were found.")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d["latitude"] = pd.to_numeric(d["latitude"], errors="coerce")
    d["longitude"] = pd.to_numeric(d["longitude"], errors="coerce")
    if d["date"].isna().any():
        raise ValueError(f"{variable} contains invalid dates.")
    if not d["date"].dt.is_month_start.all():
        raise ValueError(f"{variable} timestamps must be month-start dates.")
    d = d[d["date"].dt.year.between(int(start_year), int(end_year))]
    if d.empty:
        raise ValueError(f"{variable} has no observations in the requested period.")
    duplicated = d.duplicated(["cell_id", "date"], keep=False)
    if duplicated.any():
        sample = d.loc[duplicated, ["cell_id", "date"]].head(5)
        keys = ", ".join(f"{r.cell_id}:{r.date:%Y-%m}" for r in sample.itertuples())
        raise ValueError(
            f"{variable} contains duplicate cell-month records ({keys}). "
            "Resolve the ingestion problem before analysis."
        )
    if d[["latitude", "longitude"]].isna().any(axis=None):
        raise ValueError(f"{variable} contains invalid cell coordinates.")
    coordinate_counts = d.groupby("cell_id")[["latitude", "longitude"]].nunique()
    if (coordinate_counts > 1).any(axis=None):
        raise ValueError(f"{variable} cell IDs do not map to stable coordinates.")
    if (d["value"].dropna() < 0).any() and variable == "PRECTOTCORR":
        raise ValueError("PRECTOTCORR contains negative precipitation rates.")
    full_index = pd.date_range(
        f"{int(start_year)}-01-01", f"{int(end_year)}-12-01", freq="MS"
    )
    cells = {}
    for cell_id, group in d.groupby("cell_id", sort=True):
        series = group.set_index("date")["value"].sort_index().reindex(full_index)
        cells[str(cell_id)] = {
            "series": series.astype(float),
            "latitude": float(group["latitude"].iloc[0]),
            "longitude": float(group["longitude"].iloc[0]),
            "unit": str(group["unit"].dropna().iloc[0]) if group["unit"].notna().any() else None,
        }
    return cells, full_index


def _calendar_month_zscore(series, baseline, min_base_years):
    """Calendar-month standardisation. No values are filled."""
    means, stds, counts = {}, {}, {}
    base_mask = series.index.year.to_series(index=series.index).between(
        int(baseline[0]), int(baseline[1])
    ).to_numpy()
    for month in range(1, 13):
        sample = series.iloc[np.flatnonzero(base_mask & (series.index.month == month))].dropna()
        counts[month] = int(len(sample))
        if len(sample) < min_base_years:
            means[month], stds[month] = np.nan, np.nan
            continue
        sd = float(sample.std(ddof=1))
        means[month] = float(sample.mean())
        stds[month] = sd if np.isfinite(sd) and sd > 0 else np.nan
    z = pd.Series(np.nan, index=series.index, dtype=float)
    for month in range(1, 13):
        if np.isfinite(stds[month]):
            idx = series.index.month == month
            z.loc[idx] = (series.loc[idx] - means[month]) / stds[month]
    return z, {"n_by_calendar_month": counts, "mean": means, "sd": stds}


def _spi3(precip_monthly_mm, baseline, min_base_years):
    """Fit separate zero-adjusted gamma distributions for each calendar month."""
    accumulation = precip_monthly_mm.rolling(window=3, min_periods=3).sum()
    spi = pd.Series(np.nan, index=accumulation.index, dtype=float)
    fit_info = {}
    baseline_years = (int(baseline[0]), int(baseline[1]))
    for month in range(1, 13):
        selected = (
            (accumulation.index.year >= baseline_years[0])
            & (accumulation.index.year <= baseline_years[1])
            & (accumulation.index.month == month)
        )
        sample = accumulation.loc[selected].dropna().to_numpy(dtype=float)
        info = {"n_baseline": int(len(sample)), "zero_probability": None, "shape": None, "scale": None, "status": "insufficient_baseline"}
        if len(sample) < min_base_years:
            fit_info[month] = info
            continue
        if np.any(sample < 0):
            raise ValueError("Three-month precipitation accumulation contains negative values.")
        zero_probability = float(np.mean(sample <= 0))
        positive = sample[sample > 0]
        if len(positive) < max(10, min_base_years // 2):
            info["status"] = "insufficient_positive_baseline_values"
            fit_info[month] = info
            continue
        try:
            shape, _, scale = gamma.fit(positive, floc=0)
            if not (np.isfinite(shape) and np.isfinite(scale) and shape > 0 and scale > 0):
                raise ValueError("non-finite gamma parameters")
        except Exception as exc:
            info["status"] = f"fit_failed: {type(exc).__name__}"
            fit_info[month] = info
            continue

        all_months = accumulation.index.month == month
        values = accumulation.loc[all_months]
        cdf = zero_probability + (1.0 - zero_probability) * gamma.cdf(
            values.clip(lower=0).to_numpy(dtype=float), a=shape, loc=0, scale=scale
        )
        cdf = np.clip(cdf, 1e-6, 1 - 1e-6)
        spi.loc[all_months] = norm.ppf(cdf)
        info.update({
            "zero_probability": zero_probability,
            "shape": float(shape),
            "scale": float(scale),
            "status": "fitted",
        })
        fit_info[month] = info
    return spi, accumulation, fit_info


def _annual_event_frequency(event, min_valid_months):
    rows = []
    years = range(int(event.index.year.min()), int(event.index.year.max()) + 1)
    for year in years:
        values = event.loc[event.index.year == year]
        valid = values.dropna()
        n = int(len(valid))
        count = int((valid == 1).sum())
        frequency = 100.0 * count / n if n >= min_valid_months else np.nan
        rows.append({
            "year": int(year),
            "n_months_assessed": n,
            "n_hot_dry_months": count if n >= min_valid_months else np.nan,
            "hot_dry_frequency_pct": frequency,
        })
    return pd.DataFrame(rows).set_index("year")


def compound_hot_dry_analysis(
    temperature_frame,
    precipitation_frame,
    start_year,
    end_year,
    baseline=DEFAULT_BASE_PERIOD,
    heat_z_threshold=DEFAULT_HEAT_Z_THRESHOLD,
    spi3_threshold=DEFAULT_SPI3_THRESHOLD,
    min_base_years=DEFAULT_MIN_BASE_YEARS,
    min_valid_months_per_year=DEFAULT_MIN_VALID_MONTHS_PER_YEAR,
    alpha=0.05,
):
    """Calculate monthly and annual compound hot-dry indicators by native grid cell.

    Spatial significance uses Benjamini-Yekutieli (BY) adjusted p-values as the
    primary evidence class because the field contains spatially dependent tests.
    Benjamini-Hochberg (BH) is retained as a less-conservative sensitivity column.
    """
    start_year, end_year = int(start_year), int(end_year)
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    if baseline[0] < start_year or baseline[1] > end_year or baseline[0] > baseline[1]:
        raise ValueError("The baseline period must lie within the requested analysis period.")
    if min_base_years < 10:
        raise ValueError("min_base_years must be at least 10.")
    if min_valid_months_per_year < 1 or min_valid_months_per_year > 12:
        raise ValueError("min_valid_months_per_year must be between 1 and 12.")

    temperature_cells, temp_index = _prepare_cells(
        temperature_frame, "T2M", start_year, end_year
    )
    precipitation_cells, precip_index = _prepare_cells(
        precipitation_frame, "PRECTOTCORR", start_year, end_year
    )
    if not temp_index.equals(precip_index):
        raise AssertionError("Internal monthly indexes should be identical.")
    common_ids = sorted(set(temperature_cells) & set(precipitation_cells))
    if not common_ids:
        raise ValueError("Temperature and precipitation datasets have no common grid-cell IDs.")

    monthly_outputs, annual_outputs, trend_rows, cell_diagnostics = [], [], [], []
    for cell_id in common_ids:
        t = temperature_cells[cell_id]
        p = precipitation_cells[cell_id]
        if not np.allclose(
            [t["latitude"], t["longitude"]],
            [p["latitude"], p["longitude"]],
            atol=1e-4,
        ):
            raise ValueError(f"Cell coordinates do not match between variables for {cell_id}.")

        heat_z, heat_fit = _calendar_month_zscore(
            t["series"], baseline, min_base_years
        )
        # PRECTOTCORR is a monthly mean daily rate (mm/day), not a monthly total.
        # Convert to a monthly accumulation before computing SPI-3.
        precip_total = p["series"] * pd.Series(
            p["series"].index.days_in_month, index=p["series"].index, dtype=float
        )
        spi, precip_3m, spi_fit = _spi3(precip_total, baseline, min_base_years)

        event = pd.Series(np.nan, index=temp_index, dtype=float)
        valid = heat_z.notna() & spi.notna()
        event.loc[valid] = (
            (heat_z.loc[valid] >= float(heat_z_threshold))
            & (spi.loc[valid] <= float(spi3_threshold))
        ).astype(float)

        monthly = pd.DataFrame({
            "date": temp_index,
            "cell_id": cell_id,
            "latitude": t["latitude"],
            "longitude": t["longitude"],
            "t2m_c": t["series"].to_numpy(),
            "temperature_anomaly_z": heat_z.to_numpy(),
            "precipitation_3m_mm": precip_3m.to_numpy(),
            "spi3": spi.to_numpy(),
            "compound_hot_dry": event.to_numpy(),
        })
        annual = _annual_event_frequency(event, min_valid_months_per_year)
        annual.insert(0, "cell_id", cell_id)
        annual.insert(1, "latitude", t["latitude"])
        annual.insert(2, "longitude", t["longitude"])

        annual_series = annual["hot_dry_frequency_pct"]
        annual_series.index = annual.index
        mk = engine.mann_kendall(
            annual_series, alpha=alpha, autocorrelation="ar1_neff"
        )
        trend_rows.append({
            "cell_id": cell_id,
            "latitude": t["latitude"],
            "longitude": t["longitude"],
            "n_years": int(mk["n"]),
            "year_span": int(mk["n_span"]),
            "year_coverage": float(mk["coverage"]),
            "sen_frequency_change_pp_per_decade": engine.sens_slope_per_decade(annual_series),
            "sen_ci_low_pp_per_decade": float(mk["slope_ci_low"] * 10) if np.isfinite(mk["slope_ci_low"]) else np.nan,
            "sen_ci_high_pp_per_decade": float(mk["slope_ci_high"] * 10) if np.isfinite(mk["slope_ci_high"]) else np.nan,
            "kendall_tau": mk["tau"],
            "mk_z": mk["z"],
            "mk_p": mk["p"],
            "variance_factor": mk["variance_factor"],
            "lag1_autocorrelation": mk["rho1"],
            "trend": mk["trend"],
            "mk_reason": mk["reason"],
        })
        n_fit = sum(item["status"] == "fitted" for item in spi_fit.values())
        cell_diagnostics.append({
            "cell_id": cell_id,
            "temperature_baseline_counts": heat_fit["n_by_calendar_month"],
            "spi3_baseline_fits_succeeded": int(n_fit),
            "spi3_month_fit_status": {str(k): v["status"] for k, v in spi_fit.items()},
            "n_valid_heat_months": int(heat_z.notna().sum()),
            "n_valid_spi3_months": int(spi.notna().sum()),
            "n_compound_classified_months": int(event.notna().sum()),
            "n_hot_dry_months": int(event.eq(1).sum()),
        })
        monthly_outputs.append(monthly)
        annual_outputs.append(annual.reset_index(names="year"))

    trends = pd.DataFrame(trend_rows)
    if trends.empty:
        raise ValueError("No cell-level trend results could be generated.")
    pvalues = trends["mk_p"].to_numpy(dtype=float)
    trends["mk_p_fdr_by"] = engine.fdr_adjust(pvalues, alpha=alpha, method="by")
    trends["mk_p_fdr_bh"] = engine.fdr_adjust(pvalues, alpha=alpha, method="bh")
    trends["evidence_class_by"] = np.select(
        [
            trends["trend"].eq("insufficient_data"),
            trends["mk_p_fdr_by"].lt(alpha),
            trends["mk_p"].lt(alpha),
        ],
        [
            "insufficient_data",
            "significant_after_by",
            "significant_before_fdr_only",
        ],
        default="not_significant",
    )
    trends["evidence_class_bh_sensitivity"] = np.select(
        [
            trends["trend"].eq("insufficient_data"),
            trends["mk_p_fdr_bh"].lt(alpha),
            trends["mk_p"].lt(alpha),
        ],
        [
            "insufficient_data",
            "significant_after_bh",
            "significant_before_fdr_only",
        ],
        default="not_significant",
    )

    metadata = {
        "analysis": "retrospective_compound_hot_dry_frequency",
        "start_year": start_year,
        "end_year": end_year,
        "baseline_period": [int(baseline[0]), int(baseline[1])],
        "heat_indicator": "T2M calendar-month standardized anomaly",
        "heat_z_threshold": float(heat_z_threshold),
        "precipitation_input": "NASA POWER PRECTOTCORR monthly mean daily rate in mm/day",
        "precipitation_conversion": "monthly mean daily rate multiplied by calendar days in month",
        "drought_indicator": "SPI-3 from trailing three-month precipitation totals",
        "spi3_threshold": float(spi3_threshold),
        "spi_distribution": "zero-adjusted gamma fitted separately by ending calendar month",
        "minimum_baseline_values_per_calendar_month": int(min_base_years),
        "minimum_assessed_months_per_year": int(min_valid_months_per_year),
        "minimum_valid_annual_years": int(engine.MIN_VALID_YEARS),
        "minimum_annual_year_coverage": float(engine.MIN_YEAR_COVERAGE),
        "trend_test": "two-sided Mann-Kendall with AR(1) effective-sample-size variance adjustment",
        "slope": "Sen's slope of annual percentage of assessed months classified compound hot-dry, per decade",
        "spatial_multiple_testing_primary": "Benjamini-Yekutieli",
        "spatial_multiple_testing_sensitivity": "Benjamini-Hochberg",
        "n_temperature_cells": int(len(temperature_cells)),
        "n_precipitation_cells": int(len(precipitation_cells)),
        "n_common_cells": int(len(common_ids)),
        "temperature_only_cells": sorted(set(temperature_cells) - set(common_ids)),
        "precipitation_only_cells": sorted(set(precipitation_cells) - set(common_ids)),
        "n_cells_with_spi3_all_month_fits": int(sum(
            item["spi3_baseline_fits_succeeded"] == 12 for item in cell_diagnostics
        )),
        "interpretation_limit": (
            "A retrospective monthly compound climate-stress indicator. It is not a heatwave "
            "definition, impact estimate, soil-moisture index, or operational forecast."
        ),
    }
    return (
        pd.concat(monthly_outputs, ignore_index=True),
        pd.concat(annual_outputs, ignore_index=True),
        trends.sort_values(["latitude", "longitude"]).reset_index(drop=True),
        metadata,
        cell_diagnostics,
    )
