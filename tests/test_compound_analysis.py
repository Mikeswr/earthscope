import numpy as np
import pandas as pd
import pytest

from spatial.compound import compound_hot_dry_analysis


def sample_climate_frames(start_year=1981, end_year=2025):
    rng = np.random.default_rng(20261114)
    dates = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS")
    temperature_rows, precipitation_rows = [], []
    for cell_id, lat, lon, warm_shift in [
        ("5.7500_-0.6250", 5.75, -0.625, 0.0),
        ("6.2500_-1.2500", 6.25, -1.25, 0.15),
    ]:
        t2m = (
            27.0
            + 2.2 * np.sin(2 * np.pi * (dates.month.to_numpy() - 1) / 12)
            + 0.018 * (dates.year.to_numpy() - 1981)
            + warm_shift
            + rng.normal(0, 0.25, len(dates))
        )
        seasonal_scale = np.where(np.isin(dates.month, [6, 7, 8, 9]), 1.4, 0.7)
        daily_rate = rng.gamma(shape=2.2, scale=seasonal_scale, size=len(dates))
        # Introduce a repeatable late-record dry/warm signal for the first cell.
        if cell_id == "5.7500_-0.6250":
            late = dates.year >= 2010
            t2m[late] += 0.7
            dry_season = late & np.isin(dates.month, [6, 7, 8, 9])
            daily_rate[dry_season] *= 0.35

        for date, temp, rain in zip(dates, t2m, daily_rate):
            temperature_rows.append({
                "date": date, "variable": "T2M", "value": temp,
                "latitude": lat, "longitude": lon, "cell_id": cell_id,
                "unit": "C",
            })
            precipitation_rows.append({
                "date": date, "variable": "PRECTOTCORR", "value": rain,
                "latitude": lat, "longitude": lon, "cell_id": cell_id,
                "unit": "mm/day",
            })
    return pd.DataFrame(temperature_rows), pd.DataFrame(precipitation_rows)


def test_compound_analysis_returns_cell_month_and_annual_products():
    temp, rain = sample_climate_frames()
    monthly, annual, trends, metadata, diagnostics = compound_hot_dry_analysis(
        temp, rain, 1981, 2025
    )
    assert len(monthly) == 2 * 45 * 12
    assert set(monthly.cell_id) == set(temp.cell_id.unique())
    assert set(monthly.compound_hot_dry.dropna().unique()).issubset({0.0, 1.0})
    assert (monthly.precipitation_3m_mm.dropna() > 0).all()
    assert len(annual) == 2 * 45
    assert set(annual.columns) >= {"year", "n_months_assessed", "hot_dry_frequency_pct"}
    assert len(trends) == 2
    assert trends.mk_p_fdr_by.notna().all()
    assert trends.mk_p_fdr_bh.notna().all()
    assert metadata["spi_distribution"].startswith("zero-adjusted gamma")
    assert metadata["n_common_cells"] == 2
    assert len(diagnostics) == 2
    assert all(d["spi3_baseline_fits_succeeded"] == 12 for d in diagnostics)


def test_compound_analysis_preserves_missing_observations():
    temp, rain = sample_climate_frames()
    temp.loc[(temp.cell_id == "5.7500_-0.6250") & (temp.date == "2005-05-01"), "value"] = np.nan
    rain.loc[(rain.cell_id == "6.2500_-1.2500") & (rain.date == "2008-08-01"), "value"] = np.nan
    monthly, _, _, _, _ = compound_hot_dry_analysis(temp, rain, 1981, 2025)
    t_missing = monthly.loc[
        (monthly.cell_id == "5.7500_-0.6250") & (monthly.date == "2005-05-01")
    ].iloc[0]
    p_missing = monthly.loc[
        (monthly.cell_id == "6.2500_-1.2500") & (monthly.date == "2008-08-01")
    ].iloc[0]
    assert np.isnan(t_missing.temperature_anomaly_z)
    assert np.isnan(t_missing.compound_hot_dry)
    assert np.isnan(p_missing.precipitation_3m_mm)
    assert np.isnan(p_missing.spi3)
    assert np.isnan(p_missing.compound_hot_dry)


def test_compound_analysis_rejects_duplicate_cell_month():
    temp, rain = sample_climate_frames()
    temp = pd.concat([temp, temp.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate cell-month"):
        compound_hot_dry_analysis(temp, rain, 1981, 2025)


def test_compound_analysis_requires_baseline_inside_period():
    temp, rain = sample_climate_frames(start_year=2000, end_year=2025)
    with pytest.raises(ValueError, match="baseline period"):
        compound_hot_dry_analysis(temp, rain, 2000, 2025)


def test_compound_runner_cli_imports_and_exposes_help(capsys):
    from scripts.run_compound_analysis import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "compound hot-dry analysis" in capsys.readouterr().out.lower()
