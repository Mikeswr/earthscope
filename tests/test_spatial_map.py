from tests.test_spatial_analysis import sample_grid
from spatial.map import build_regional_grid_map


def test_mean_map_contains_native_grid_rectangles_and_colour_legend():
    frame = sample_grid()
    fmap, summary, spacing = build_regional_grid_map(frame, "T2M", 2010, 2019, "Mean value")
    rendered = fmap.get_root().render()
    assert len(summary) == 4
    assert spacing == (0.5, 0.5)
    assert "T2M period mean" in rendered
    assert "OpenStreetMap" in rendered


def test_trend_map_contains_evidence_legend_and_cell_details():
    frame = sample_grid()
    fmap, summary, spacing = build_regional_grid_map(frame, "T2M", 2000, 2024, "Trend evidence")
    rendered = fmap.get_root().render()
    assert len(summary) == 4
    assert "Trend evidence" in rendered
    assert "significant after FDR" in rendered
