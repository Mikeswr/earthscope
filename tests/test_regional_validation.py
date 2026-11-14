import numpy as np
import pandas as pd

from spatial.validation import validate_regional_frame


def sample_frame():
    dates = pd.date_range("2020-01-01", "2021-12-01", freq="MS")
    rows = []
    for cell_id, lat, lon in [("6.0000_-1.0000", 6.0, -1.0), ("6.5000_-0.5000", 6.5, -0.5)]:
        for date in dates:
            rows.append({
                "date": date, "variable": "T2M", "value": 27.0 + 0.1 * np.sin(date.month),
                "latitude": lat, "longitude": lon, "cell_id": cell_id,
                "unit": "C", "unit_source": "response_metadata",
                "source": "NASA POWER regional monthly",
                "data_kind": "gridded_estimate_not_station_observation",
            })
    return pd.DataFrame(rows)


def test_valid_regional_grid_is_eligible_without_mutating_input():
    frame = sample_frame()
    before = frame.copy(deep=True)
    report = validate_regional_frame(frame, "T2M", 2020, 2021)
    assert report["status"] == "pass"
    assert report["analysis_eligible"] is True
    assert report["cells"] == 2
    assert report["valid_observations"] == 48
    pd.testing.assert_frame_equal(frame, before)


def test_missing_months_are_reported_and_never_filled():
    frame = sample_frame()
    frame.loc[0, "value"] = np.nan
    report = validate_regional_frame(frame, "T2M", 2020, 2021)
    assert report["status"] == "warn"
    assert report["missing_observations"] == 1
    assert report["analysis_eligible"] is True
    assert report["minimum_cell_valid_fraction"] < 1


def test_duplicate_cell_month_blocks_analysis():
    frame = sample_frame()
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    report = validate_regional_frame(frame, "T2M", 2020, 2021)
    assert report["status"] == "fail"
    assert report["analysis_eligible"] is False
    assert report["duplicate_cell_month_records"] == 2


def test_implausible_values_block_analysis():
    frame = sample_frame()
    frame.loc[0, "value"] = 999
    report = validate_regional_frame(frame, "T2M", 2020, 2021)
    assert report["status"] == "fail"
    assert report["out_of_range_observations"] == 1
    assert report["analysis_eligible"] is False


def test_wrong_units_block_analysis():
    frame = sample_frame()
    frame["unit"] = "K"
    report = validate_regional_frame(frame, "T2M", 2020, 2021)
    assert report["status"] == "fail"
    assert report["analysis_eligible"] is False


def test_mixed_variable_dataset_blocks_analysis():
    frame = sample_frame()
    frame.loc[0, "variable"] = "RH2M"
    report = validate_regional_frame(frame, "T2M", 2020, 2021)
    assert report["status"] == "fail"
    assert report["analysis_eligible"] is False
