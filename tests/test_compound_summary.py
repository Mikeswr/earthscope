import pandas as pd
import pytest

from spatial.compound_summary import summarise_compound_outputs


def sample_annual():
    return pd.DataFrame([
        {"year": 2000, "cell_id": "c1", "latitude": 6.0, "longitude": -1.0,
         "n_months_assessed": 12, "n_hot_dry_months": 2, "hot_dry_frequency_pct": 100*2/12},
        {"year": 2001, "cell_id": "c1", "latitude": 6.0, "longitude": -1.0,
         "n_months_assessed": 12, "n_hot_dry_months": 0, "hot_dry_frequency_pct": 0.0},
        {"year": 2000, "cell_id": "c2", "latitude": 6.5, "longitude": -1.5,
         "n_months_assessed": 12, "n_hot_dry_months": 1, "hot_dry_frequency_pct": 100/12},
        {"year": 2001, "cell_id": "c2", "latitude": 6.5, "longitude": -1.5,
         "n_months_assessed": 12, "n_hot_dry_months": 1, "hot_dry_frequency_pct": 100/12},
    ])


def test_summaries_preserve_cells_and_count_annual_events():
    annual, cells, geojson, meta = summarise_compound_outputs(sample_annual(), pd.DataFrame())
    y2000 = annual.set_index("year").loc[2000]
    assert y2000.n_grid_cells_assessed == 2
    assert y2000.total_compound_hot_dry_cell_months == 3
    assert y2000.n_cells_with_at_least_one_event == 2
    assert y2000.pct_cells_with_at_least_one_event == 100
    c1 = cells.set_index("cell_id").loc["c1"]
    assert c1.total_compound_hot_dry_months == 2
    assert c1.n_years_with_at_least_one_event == 1
    assert c1.pct_assessed_years_with_no_event == 50
    assert len(geojson["features"]) == 2
    assert meta["n_grid_cells"] == 2
    assert "not an area-weighted national estimate" in meta["spatial_inference"]
    assert meta["domain_aggregate_trend"]["n_valid_years"] == 2
    assert meta["domain_aggregate_trend"]["mann_kendall_p"] is not None
    assert meta["domain_aggregate_trend"]["autocorrelation_method"].startswith("AR(1)")


def test_summaries_join_cell_trend_results():
    trends = pd.DataFrame([
        {"cell_id": "c1", "mk_p": 0.01, "mk_p_fdr_by": 0.5, "evidence_class_by": "not_significant"},
        {"cell_id": "c2", "mk_p": 0.7, "mk_p_fdr_by": 1.0, "evidence_class_by": "not_significant"},
    ])
    _, cells, _, _ = summarise_compound_outputs(sample_annual(), trends)
    assert cells.set_index("cell_id").loc["c1", "mk_p"] == 0.01
    assert cells.set_index("cell_id").loc["c2", "mk_p_fdr_by"] == 1.0


def test_summaries_reject_duplicate_cell_year_records():
    d = sample_annual()
    d = pd.concat([d, d.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate cell-year"):
        summarise_compound_outputs(d, pd.DataFrame())
