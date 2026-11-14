import numpy as np
import pandas as pd
import pytest

from spatial.imerg_validation import compare_power_imerg, write_imerg_comparison


def fixture_frames(n_months=24):
    dates = pd.date_range("2000-01-01", periods=n_months, freq="MS")
    grid_rows = [
        {"cell_id": "6.0000_-1.0000", "latitude": 6.0, "longitude": -1.0,
         "latitude_spacing_degrees": 0.5, "longitude_spacing_degrees": 0.625},
        {"cell_id": "6.5000_-0.5000", "latitude": 6.5, "longitude": -0.5,
         "latitude_spacing_degrees": 0.5, "longitude_spacing_degrees": 0.625},
    ]
    power_rows, imerg_rows = [], []
    for ci, cell in enumerate(grid_rows):
        for i, date in enumerate(dates):
            daily = 1.5 + 0.2 * np.sin(2 * np.pi * (date.month - 1) / 12) + 0.1 * ci + 0.005 * i
            hours = date.days_in_month * 24
            imerg_rate = (daily * 1.05) / 24
            power_rows.append({
                "date": date, "variable": "PRECTOTCORR", "value": daily,
                "latitude": cell["latitude"], "longitude": cell["longitude"],
                "cell_id": cell["cell_id"], "unit": "mm/day",
            })
            imerg_rows.append({
                "date": date, "cell_id": cell["cell_id"],
                "latitude": cell["latitude"], "longitude": cell["longitude"],
                "precipitation_mean": imerg_rate,
                "precipitation_count": 30,
                "gaugeRelativeWeighting_mean": 40.0,
                "precipitationQualityIndex_mean": 3.0,
                "randomError_mean": 0.01,
                "imerg_month_hours": hours,
                "imerg_precipitation_mm_month_total": imerg_rate * hours,
                "imerg_collection_id": "NASA/GPM_L3/IMERG_MONTHLY_V07",
            })
    return (
        pd.DataFrame(power_rows),
        pd.DataFrame(imerg_rows),
        pd.DataFrame(grid_rows),
    )


def test_matched_support_comparison_converts_monthly_units_and_reports_metrics():
    power, imerg, grid = fixture_frames()
    result = compare_power_imerg(power, imerg, grid, "2000-01-01", "2001-12-01")
    assert len(result["paired_monthly"]) == 48
    assert len(result["cell_metrics"]) == 2
    assert len(result["seasonal_metrics"]) == 8
    assert len(result["complete_annual_pairs"]) == 4
    assert result["metadata"]["analysis_eligible"] is True
    assert result["metadata"]["overall"]["n_valid_paired_cell_months"] == 48
    assert result["metadata"]["overall"]["pooled_all_cell_month_metrics_descriptive_only"]["bias_imerg_minus_power_mm"] > 0
    february = result["paired_monthly"].loc[
        result["paired_monthly"]["date"].eq("2000-02-01")
    ].iloc[0]
    assert february["imerg_month_total_mm"] == pytest.approx(
        february["precipitation_mean"] * 29 * 24
    )
    assert february["power_month_total_mm"] == pytest.approx(
        february["power_daily_rate_mm_day"] * 29
    )
    assert "not independent station validation" in result["metadata"]["interpretation"].lower()


def test_missing_imerg_months_are_not_filled_and_reduce_coverage():
    power, imerg, grid = fixture_frames()
    mask = ~(
        imerg["cell_id"].eq("6.0000_-1.0000")
        & imerg["date"].between("2000-01-01", "2000-05-01")
    )
    imerg = imerg.loc[mask].copy()
    result = compare_power_imerg(power, imerg, grid, "2000-01-01", "2001-12-01")
    coverage = result["coverage"].set_index("cell_id")
    assert coverage.loc["6.0000_-1.0000", "valid_months"] == 19
    assert coverage.loc["6.0000_-1.0000", "eligible_at_coverage_threshold"] == False
    assert len(result["paired_monthly"]) == 43
    assert result["metadata"]["analysis_eligible"] is False


def test_duplicate_imerg_cell_month_is_rejected():
    power, imerg, grid = fixture_frames()
    imerg = pd.concat([imerg, imerg.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate cell-month"):
        compare_power_imerg(power, imerg, grid, "2000-01-01", "2001-12-01")


def test_mismatched_cell_coordinates_are_rejected():
    power, imerg, grid = fixture_frames()
    imerg.loc[0, "latitude"] += 0.1
    with pytest.raises(ValueError, match="coordinates do not match"):
        compare_power_imerg(power, imerg, grid, "2000-01-01", "2001-12-01")


def test_negative_imerg_precipitation_is_rejected():
    power, imerg, grid = fixture_frames()
    imerg.loc[0, "precipitation_mean"] = -1
    with pytest.raises(ValueError, match="negative precipitation rates"):
        compare_power_imerg(power, imerg, grid, "2000-01-01", "2001-12-01")


def test_inconsistent_imerg_monthly_total_is_rejected():
    power, imerg, grid = fixture_frames()
    imerg.loc[0, "imerg_precipitation_mm_month_total"] += 10
    with pytest.raises(ValueError, match="rate-to-total conversion"):
        compare_power_imerg(power, imerg, grid, "2000-01-01", "2001-12-01")


def test_comparison_writer_saves_reproducible_outputs(tmp_path):
    power, imerg, grid = fixture_frames()
    result = compare_power_imerg(power, imerg, grid, "2000-01-01", "2001-12-01")
    outputs = write_imerg_comparison(result, tmp_path)
    assert "metadata" in outputs and "report" in outputs
    assert (tmp_path / "imerg_power_comparison_metadata.json").exists()
    report = (tmp_path / "imerg_power_comparison_report.md").read_text()
    assert "cross-product assessment" in report.lower()
    assert "not independent station validation" in report.lower()
