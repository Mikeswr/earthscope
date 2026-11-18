from fastapi.testclient import TestClient

from api import main


client = TestClient(main.app)


def test_health_endpoint_reports_service():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "earthscope-api"
    assert payload["version"] == main.API_VERSION


def test_locations_endpoint_uses_configured_locations(monkeypatch):
    monkeypatch.setattr(
        main.config,
        "load_locations",
        lambda: {"Accra": (5.618, -0.171), "Kumasi": (6.695, -1.616)},
    )
    response = client.get("/api/v1/locations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["locations"][0] == {
        "name": "Accra",
        "latitude": 5.618,
        "longitude": -0.171,
    }


def test_variables_endpoint_returns_supported_codes_and_units():
    response = client.get("/api/v1/variables")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 7
    variables = {item["code"]: item for item in payload["variables"]}
    assert variables["T2M"]["unit"] == "C"
    assert variables["PRECTOTCORR"]["unit"] == "mm/day"
    assert variables["ALLSKY_SFC_SW_DWN"]["source"] == "NASA POWER"


def test_metadata_endpoint_preserves_source_provenance(monkeypatch):
    monkeypatch.setattr(
        main,
        "_metadata",
        lambda: {"built_utc": "2026-11-10T12:55:28+00:00", "rows": 18900},
    )
    response = client.get("/api/v1/metadata")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "NASA POWER"
    assert payload["data_kind"] == "gridded_estimate_not_station_observation"
    assert payload["metadata"]["rows"] == 18900


def test_trends_endpoint_filters_existing_results(monkeypatch):
    records = [
        {
            "location": "Accra",
            "variable": "T2M",
            "sen_per_decade": 0.2,
            "significant_fdr": True,
        },
        {
            "location": "Kumasi",
            "variable": "T2M",
            "sen_per_decade": 0.1,
            "significant_fdr": False,
        },
    ]
    monkeypatch.setattr(main, "_trend_records", lambda: (records, list(records[0])))
    response = client.get(
        "/api/v1/trends",
        params={"location": "Accra", "variable": "T2M", "significant_only": "true"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["location"] == "Accra"
    assert payload["results"][0]["sen_per_decade"] == 0.2


def test_trends_endpoint_rejects_unknown_location_and_variable():
    bad_location = client.get("/api/v1/trends", params={"location": "Cape Coast"})
    bad_variable = client.get("/api/v1/trends", params={"variable": "UNKNOWN"})
    assert bad_location.status_code == 422
    assert bad_variable.status_code == 422

def test_real_processed_trend_matches_lumosx_contract():
    """Exercise the committed processed data through the API, not a mocked row."""
    main._trend_records.cache_clear()
    response = client.get(
        "/api/v1/trends",
        params={"location": "Accra", "variable": "T2M"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data_kind"] == "gridded_estimate_not_station_observation"

    result = payload["results"][0]
    required_fields = {
        "location",
        "variable",
        "unit",
        "first_year",
        "last_year",
        "sen_per_decade",
        "mk_trend",
        "mk_p_fdr",
        "significant_fdr",
        "evidence_class",
    }
    assert required_fields.issubset(result)
    assert result["location"] == "Accra"
    assert result["variable"] == "T2M"
    assert isinstance(result["first_year"], int)
    assert isinstance(result["last_year"], int)
    assert isinstance(result["sen_per_decade"], (int, float))
    assert isinstance(result["mk_p_fdr"], (int, float))
    assert isinstance(result["significant_fdr"], bool)
    assert result["evidence_class"]
    main._trend_records.cache_clear()


def test_all_35_location_variable_combinations_return_real_processed_rows():
    """Verify every configured location-variable pair resolves to one processed result."""
    main._trend_records.cache_clear()
    locations = client.get("/api/v1/locations")
    variables = client.get("/api/v1/variables")
    assert locations.status_code == 200
    assert variables.status_code == 200

    location_names = [item["name"] for item in locations.json()["locations"]]
    variable_codes = [item["code"] for item in variables.json()["variables"]]
    assert len(location_names) == 5
    assert len(variable_codes) == 7

    checked = set()
    for location_name in location_names:
        for variable_code in variable_codes:
            response = client.get(
                "/api/v1/trends",
                params={"location": location_name, "variable": variable_code},
            )
            assert response.status_code == 200, (location_name, variable_code, response.text)
            payload = response.json()
            assert payload["count"] == 1, (location_name, variable_code, payload["count"])
            result = payload["results"][0]
            assert result["location"] == location_name
            assert result["variable"] == variable_code
            assert result["source"] == "NASA POWER"
            assert result["data_kind"] == "gridded_estimate_not_station_observation"
            assert result["first_year"] <= result["last_year"]
            checked.add((location_name, variable_code))

    assert len(checked) == 35
    main._trend_records.cache_clear()
