import pandas as pd
import pytest

from spatial.power_regional import (
    RegionalPowerError,
    available_years,
    build_request_params,
    build_tiles,
    estimate_grid_spacing,
    parse_regional_payload,
)


def payload(variable="T2M"):
    return {
        "type": "FeatureCollection",
        "header": {"fill_value": -999.0},
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-1.0, 6.0]},
                "properties": {
                    "parameter": {variable: {"202401": 28.1, "202402": 29.2, "202413": 28.6}}
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-0.5, 6.0]},
                "properties": {
                    "parameter": {variable: {"202401": 27.8, "202402": -999.0}}
                },
            },
        ],
    }


def test_build_tiles_cover_bbox_without_gaps_or_overlaps():
    tiles = build_tiles((-3.2, 4.7, 1.2, 11.1), max_span=4.0)
    assert len(tiles) == 4
    assert tiles[0]["west"] == -3.2
    assert tiles[-1]["east"] == 1.2
    assert tiles[-1]["north"] == 11.1
    assert all(t["east"] - t["west"] <= 4.0 for t in tiles)
    assert all(t["north"] - t["south"] <= 4.0 for t in tiles)


def test_build_tiles_reject_invalid_bbox_and_oversized_span():
    with pytest.raises(ValueError):
        build_tiles((2, 5, 1, 10))
    with pytest.raises(ValueError):
        build_tiles(max_span=5)


def test_request_is_one_parameter_and_uses_regional_bounds():
    tile = {"west": -3.0, "south": 4.0, "east": 1.0, "north": 8.0}
    params = build_request_params("T2M", tile, 1981, 2025)
    assert params["parameters"] == "T2M"
    assert params["latitude-min"] == 4.0
    assert params["longitude-max"] == 1.0
    assert params["start"] == 1981 and params["end"] == 2025


def test_parse_geojson_cells_months_and_fill_values():
    frame = parse_regional_payload(payload(), "T2M", "test-tile")
    assert len(frame) == 3
    assert set(frame["cell_id"]) == {"6.0000_-1.0000", "6.0000_-0.5000"}
    assert pd.Timestamp("2024-01-01") in set(frame["date"])
    assert frame.loc[(frame["longitude"] == -0.5) & (frame["date"].dt.month == 2), "value"].isna().all()
    assert not (frame["date"].dt.month == 13).any()
    assert frame["source"].eq("NASA POWER regional monthly").all()
    assert frame["data_kind"].eq("gridded_estimate_not_station_observation").all()


def test_parser_rejects_non_geojson_and_missing_parameter():
    with pytest.raises(RegionalPowerError):
        parse_regional_payload({"properties": {}}, "T2M")
    bad = payload()
    del bad["features"][0]["properties"]["parameter"]["T2M"]
    with pytest.raises(RegionalPowerError):
        parse_regional_payload(bad, "T2M")


def test_parser_rejects_non_point_geometry():
    bad = payload()
    bad["features"][0]["geometry"] = {
        "type": "Polygon", "coordinates": [[[-1, 6], [-1, 7], [0, 7], [-1, 6]]]
    }
    with pytest.raises(RegionalPowerError):
        parse_regional_payload(bad, "T2M")


def test_grid_spacing_is_descriptive_and_years_ignore_missing():
    frame = parse_regional_payload(payload(), "T2M")
    spacing = estimate_grid_spacing(frame)
    assert spacing["longitude_spacing_degrees"] == pytest.approx(0.5)
    assert available_years(frame) == [2024]


def test_solar_period_does_not_claim_pre_1984():
    from spatial.power_regional import fetch_parameter
    # Guard the start-year rule through a patched fetch_tile.
    import spatial.power_regional as regional
    calls = []
    original = regional.fetch_tile

    def fake_fetch(variable, tile, start, end, session=None):
        calls.append((start, end))
        return parse_regional_payload(payload(), "T2M"), {"tile": tile}

    regional.fetch_tile = fake_fetch
    try:
        result = fetch_parameter("ALLSKY_SFC_SW_DWN", start_year=1981, end_year=1985,
                                 bbox=(-1, 5, 1, 7))
    finally:
        regional.fetch_tile = original
    assert calls and all(start == 1984 for start, _ in calls)
    assert not result.empty
