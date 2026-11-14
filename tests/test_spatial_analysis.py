import numpy as np
import pandas as pd

from spatial.analysis import cell_trend_table, grid_cell_bounds, period_cell_means


def sample_grid():
    dates = pd.date_range("2000-01-01", "2024-12-01", freq="MS")
    rows = []
    for cell_id, lat, lon, base, slope in [
        ("cell-a", 6.0, -1.0, 25.0, 0.04),
        ("cell-b", 6.0, -0.5, 27.0, 0.0),
        ("cell-c", 6.5, -1.0, 26.0, 0.0),
        ("cell-d", 6.5, -0.5, 28.0, 0.0),
    ]:
        for date in dates:
            value = base + slope * (date.year - 2000) + 0.1 * np.sin(date.month)
            rows.append({
                "date": date, "variable": "T2M", "value": value,
                "latitude": lat, "longitude": lon, "cell_id": cell_id,
                "unit": "C", "unit_source": "response_metadata",
                "source": "NASA POWER regional monthly",
                "data_kind": "gridded_estimate_not_station_observation",
                "tile_id": "fixture",
            })
    return pd.DataFrame(rows)


def test_period_means_keep_grid_cell_identity_and_month_counts():
    frame = sample_grid()
    summary = period_cell_means(frame, 2010, 2019)
    assert len(summary) == 4
    assert set(summary.n_months) == {120}
    assert summary.mean_value.notna().all()


def test_cell_trends_calculated_independently_and_fdr_adjusted():
    frame = sample_grid()
    trends = cell_trend_table(frame, "T2M")
    assert len(trends) == 4
    assert trends.mk_p_fdr.notna().all()
    rising = trends.set_index("cell_id").loc["cell-a"]
    assert rising.sen_per_decade > 0
    assert rising.evidence_class == "significant_after_fdr"


def test_grid_cell_footprints_use_returned_coordinate_spacing():
    frame = sample_grid()
    lat_spacing, lon_spacing = grid_cell_bounds(frame)
    assert lat_spacing == 0.5
    assert lon_spacing == 0.5


def test_duplicate_cell_months_are_rejected_not_averaged():
    frame = sample_grid()
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    try:
        cell_trend_table(frame, "T2M")
    except ValueError as exc:
        assert "Duplicate cell-month records" in str(exc)
    else:
        raise AssertionError("Duplicate cell-month records must block trend analysis")
