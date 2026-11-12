import pandas as pd

from spatial.analysis import filter_cells_to_boundary
from tests.test_spatial_analysis import sample_grid


def boundary_fixture():
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "Test Ghana subset"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-0.75, 5.75], [-0.25, 5.75], [-0.25, 6.75],
                    [-0.75, 6.75], [-0.75, 5.75]
                ]],
            },
        }],
    }


def test_filter_keeps_only_cell_centres_inside_boundary():
    filtered = filter_cells_to_boundary(sample_grid(), boundary_fixture())
    assert set(filtered.cell_id.unique()) == {"cell-b", "cell-d"}


def test_empty_or_missing_boundary_does_not_mutate_input():
    frame = sample_grid()
    assert len(filter_cells_to_boundary(frame, None)) == len(frame)
    assert len(filter_cells_to_boundary(frame, {"type": "FeatureCollection", "features": []})) == len(frame)


def test_map_summary_contains_only_ghana_cells_and_clipped_geometry():
    from spatial.map import build_regional_grid_map
    fmap, summary, _ = build_regional_grid_map(
        sample_grid(), "T2M", 2010, 2019,
        mode="Mean value", boundary_geojson=boundary_fixture(),
    )
    assert set(summary.cell_id) == {"cell-b", "cell-d"}
    rendered = fmap.get_root().render()
    assert "Ghana district boundaries" in rendered
