"""OpenWeather and Agromonitoring tests. NO live service is contacted.
Fixtures below are SHAPE FIXTURES written from the public documentation. They are not real responses,
so passing these tests does NOT show the integrations work against the live services."""
import json
import traceback

import pandas as pd
import pytest
import requests

from earthscope import config
from earthscope.ingest import agromonitoring as agro
from earthscope.ingest import http, openweather as owm
from scripts import check_apis

KEY = "SECRETKEY1234567890abcdef"


class Resp:
    def __init__(self, payload=None, status=200, text=None):
        self.status_code, self._p = status, payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._p is None:
            raise ValueError("no json")
        return self._p


@pytest.fixture(autouse=True)
def keys(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENWEATHER_API_KEY", KEY)
    monkeypatch.setenv("AGROMONITORING_API_KEY", KEY)
    monkeypatch.setenv("EARTHSCOPE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(http.time, "sleep", lambda s: None)


def route(monkeypatch, handler):
    calls = []

    def fake(method, url, params=None, json=None, timeout=None):
        calls.append({"method": method, "url": url, "params": dict(params or {}), "json": json})
        return handler(method, url, dict(params or {}))
    monkeypatch.setattr(http.requests, "request", fake)
    return calls


# ---------------------------------------------------------------- credentials
def test_env_var_names_are_standardised():
    assert config.ENV_OPENWEATHER == "OPENWEATHER_API_KEY" and config.ENV_AGROMONITORING == "AGROMONITORING_API_KEY"
    text = (config.ROOT / ".env.example").read_text()
    assert "OPENWEATHER_API_KEY=" in text and "AGROMONITORING_API_KEY=" in text


def test_environment_wins_then_streamlit_secrets_file(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENWEATHER_API_KEY")
    sec = tmp_path / ".streamlit"
    sec.mkdir()
    (sec / "secrets.toml").write_text('OPENWEATHER_API_KEY = "from-secrets"\n')
    monkeypatch.setattr(config, "ROOT", tmp_path)
    assert config.get_key("OPENWEATHER_API_KEY") == "from-secrets"
    monkeypatch.setenv("OPENWEATHER_API_KEY", "from-env")
    assert config.get_key("OPENWEATHER_API_KEY") == "from-env"


def test_missing_key_is_a_clear_error_without_any_request(monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY")
    calls = route(monkeypatch, lambda *a: Resp({}))
    with pytest.raises(http.ApiError, match="not set"):
        owm.day_summary(5.6, -0.19, "2020-01-15")
    assert calls == []


def test_key_never_appears_in_errors_or_tracebacks(monkeypatch):
    def boom(method, url, params):
        raise requests.ConnectionError(f"HTTPSConnectionPool(host='x'): url: /p?lat=1&appid={KEY} (Caused by ...)")
    route(monkeypatch, boom)
    with pytest.raises(http.ApiError) as e:
        owm.current_weather(5.6, -0.19)
    tb = "".join(traceback.format_exception(e.value))
    assert KEY not in str(e.value) and KEY not in tb
    route(monkeypatch, lambda m, u, p: Resp(None, 401, f"Invalid API key {KEY} appid={KEY}"))
    with pytest.raises(http.ApiError) as e2:
        agro.list_polygons()
    assert KEY not in str(e2.value) and KEY not in "".join(traceback.format_exception(e2.value))


@pytest.mark.parametrize("status,needle", [(401, "rejected"), (403, "not included in the plan"), (404, "not found")])
def test_status_codes_become_entitlement_hints(monkeypatch, status, needle):
    calls = route(monkeypatch, lambda m, u, p: Resp(None, status, "denied"))
    with pytest.raises(http.ApiError) as e:
        owm.day_summary(5.6, -0.19, "2020-01-15")
    assert e.value.status == status and needle in e.value.hint and len(calls) == 1   # no retry on 4xx


def test_rate_limit_is_retried_then_reported(monkeypatch):
    calls = route(monkeypatch, lambda m, u, p: Resp(None, 429, "slow down"))
    with pytest.raises(http.ApiError, match="rate limit"):
        agro.current_weather(5.6, -0.19)
    assert len(calls) == 3


# ---------------------------------------------------------------- OpenWeather
def day_fixture():
    return {"lat": 5.6, "lon": -0.19, "tz": "+00:00", "date": "2020-01-15", "units": "metric",
            "cloud_cover": {"afternoon": 40}, "humidity": {"afternoon": 55},
            "precipitation": {"total": 0.0}, "pressure": {"afternoon": 1011},
            "temperature": {"min": 23.1, "max": 31.4, "afternoon": 30.2, "night": 24.0, "evening": 26.5, "morning": 24.8},
            "wind": {"max": {"speed": 6.2, "direction": 200}}}


def test_openweather_request_shapes(monkeypatch):
    calls = route(monkeypatch, lambda m, u, p: Resp(day_fixture()))
    owm.day_summary(5.6, -0.19, "2020-01-15")
    c = calls[0]
    assert c["url"] == "https://api.openweathermap.org/data/3.0/onecall/day_summary"
    assert c["params"] == {"lat": 5.6, "lon": -0.19, "date": "2020-01-15", "units": "metric", "appid": KEY}
    route(monkeypatch, lambda m, u, p: Resp({"list": []}))
    calls = route(monkeypatch, lambda m, u, p: Resp({"list": []}))
    owm.history_hourly(5.6, -0.19, 1579046400, 1579057200)
    assert calls[0]["url"] == "https://history.openweathermap.org/data/2.5/history/city"
    assert calls[0]["params"]["type"] == "hour" and calls[0]["params"]["start"] == 1579046400


def test_day_summary_parser_labels_statistics_and_does_not_fill_gaps():
    f = day_fixture()
    del f["precipitation"]
    df = owm.parse_day_summary(f, "Accra", 5.6, -0.19)
    assert "precip_total" not in set(df.variable)                       # absent is not zero
    row = df[df.variable == "temp_max"].iloc[0]
    assert row.value == 31.4 and row.unit == "C" and row.statistic == "daily_maximum"
    assert row.unit_source == "response_echo_metric" and row.data_kind == "blended_measured_and_model_unverified"
    assert df[df.variable == "wind_max_speed"].iloc[0].unit == "m/s"


def test_day_summary_unit_mismatch_is_rejected():
    f = day_fixture()
    f["units"] = "standard"
    with pytest.raises(http.ApiError, match="unit mismatch"):
        owm.parse_day_summary(f, "Accra", 5.6, -0.19)


def test_history_parser_keeps_rain_absent_as_absent():
    payload = {"list": [{"dt": 1579046400, "main": {"temp": 26.0, "pressure": 1010, "humidity": 80},
                         "wind": {"speed": 3.0}, "clouds": {"all": 20}},
                        {"dt": 1579050000, "main": {"temp": 27.0}, "rain": {"1h": 0.4}}]}
    df = owm.parse_history_hourly(payload, "Accra", 5.6, -0.19)
    assert (df.variable == "rain_1h").sum() == 1 and df[df.variable == "rain_1h"].value.iat[0] == 0.4
    assert df.date.dt.tz is None and df.statistic.isin(["hourly_instantaneous", "hourly_accumulation"]).all()


# ---------------------------------------------------------------- Agromonitoring
def test_polygon_helpers_and_request_shape(monkeypatch):
    ring = agro.square_polygon(5.6, -0.19, 250)
    assert ring[0] == ring[-1] and len(ring) == 5
    with pytest.raises(ValueError):
        agro.create_polygon("x", ring[:-1])
    calls = route(monkeypatch, lambda m, u, p: Resp({"id": "abc"}, 201))
    agro.create_polygon("EarthScope", ring)
    c = calls[0]
    assert c["method"] == "POST" and c["url"].endswith("/agro/1.0/polygons")
    assert c["json"]["geo_json"]["geometry"]["type"] == "Polygon" and c["params"]["appid"] == KEY


def test_ndvi_request_uses_polyid_and_unix_times(monkeypatch):
    calls = route(monkeypatch, lambda m, u, p: Resp([]))
    agro.ndvi_history("poly1", 1704067200, 1735689600)
    assert calls[0]["url"].endswith("/agro/1.0/ndvi/history")
    assert calls[0]["params"]["polyid"] == "poly1" and calls[0]["params"]["start"] == 1704067200


def ndvi_fixture():
    return [{"dt": 1704067200, "source": "s2", "zoom": 13, "dc": 100, "cl": 0.2,
             "data": {"std": 0.1, "p75": 0.7, "min": 0.2, "max": 0.84, "median": 0.6, "p25": 0.47, "num": 8374, "mean": 0.598}},
            {"dt": 1704153600, "source": "l8", "cl": 90.0},                       # no data block
            {"dt": 1704067200, "source": "s2", "dc": 100, "cl": 0.2,
             "data": {"mean": 0.598, "median": 0.6}}]                             # same date and satellite, same mean


def test_ndvi_parser_keeps_quality_fields_skips_empty_and_collapses_repeats():
    df = agro.parse_ndvi_history(ndvi_fixture(), "poly1", "Accra", 5.6, -0.19)
    assert len(df) == 1 and df.attrs["entries_skipped_without_data"] == 1
    r = df.iloc[0]
    assert r.satellite == "s2" and r.cloud_pct == 0.2 and r.useful_area_pct == 100 and r.data_kind == "satellite_derived"
    bad = ndvi_fixture()
    bad[2]["data"]["mean"] = 0.9
    with pytest.raises(ValueError, match="conflicting"):
        agro.parse_ndvi_history(bad, "poly1", "Accra", 5.6, -0.19)


def test_agro_weather_history_converts_kelvin_explicitly_and_refuses_celsius():
    kel = [{"dt": 1620136800, "main": {"temp": 300.15, "humidity": 71, "pressure": 1015}, "wind": {"speed": 2.0}, "clouds": {"all": 1}}]
    df = agro.parse_weather_history(kel, "Accra", 5.6, -0.19)
    t = df[df.variable == "temp"].iloc[0]
    assert abs(t.value - 27.0) < 1e-9 and t.unit == "C" and t.unit_source == "kelvin_in_response_converted_to_C"
    cel = [{"dt": 1620136800, "main": {"temp": 27.0}}]
    with pytest.raises(agro.UnitError):
        agro.parse_weather_history(cel, "Accra", 5.6, -0.19)


# ---------------------------------------------------------------- probe script
def test_integrations_are_not_claimed_verified():
    assert owm.VERIFIED_AGAINST_LIVE_API is False and agro.VERIFIED_AGAINST_LIVE_API is False


def test_probe_reports_entitlement_failures_and_never_writes_the_key(monkeypatch, tmp_path):
    def handler(method, url, params):
        if "day_summary" in url:
            return Resp(None, 403, "not in plan")
        if url.endswith("/weather") and "agromonitoring" in url:
            return Resp({"main": {"temp": 300.0}})
        if "data/2.5/weather" in url:
            return Resp({"main": {"temp": 27.0}})
        if "history.openweathermap" in url:
            return Resp(None, 401, "bad key")
        if url.endswith("/weather/history"):
            return Resp([{"dt": 1705276800, "main": {"temp": 301.0}}])
        if url.endswith("/polygons") and method == "GET":
            return Resp([{"id": "poly1"}])
        if url.endswith("/ndvi/history"):
            return Resp(ndvi_fixture())
        return Resp(None, 404, "unexpected")
    route(monkeypatch, handler)
    report = check_apis.run_probes()
    by = {r["endpoint"]: r for r in report["results"]}
    assert by["onecall_3.0_day_summary"]["usable"] is False and by["onecall_3.0_day_summary"]["http_status"] == 403
    assert "entitlement" in by["onecall_3.0_day_summary"]["hint"]
    assert by["history_hourly"]["http_status"] == 401
    assert by["current_weather_2.5"]["usable"] and by["ndvi_history"]["usable"] and by["weather_history"]["usable"]
    assert report["keys_present"] == {"openweather": True, "agromonitoring": True}
    assert KEY not in json.dumps(report)
    assert check_apis.main([]) == 1                                         # any failing endpoint -> non zero exit
    assert KEY not in (config.processed_dir() / "api_probe_report.json").read_text()


def test_probe_flags_a_200_with_the_wrong_shape_as_unusable(monkeypatch):
    route(monkeypatch, lambda m, u, p: Resp({"unexpected": "shape"}))
    report = check_apis.run_probes()
    cur = [r for r in report["results"] if r["endpoint"] == "current_weather_2.5"][0]
    assert cur["http_status"] == 200 and cur["usable"] is False and "FAILED" in cur["parser_check"]


def test_satellite_polygon_reuse_and_create_within_area_limit(monkeypatch):
    calls = route(monkeypatch, lambda m, u, p: Resp([] if m == "GET" else {"id": "new-poly"}, 201 if m == "POST" else 200))
    poly = agro.find_or_create_study_polygon("Accra", 5.618, -0.171)
    assert poly["id"] == "new-poly"
    post = next(c for c in calls if c["method"] == "POST")
    coords = post["json"]["geo_json"]["geometry"]["coordinates"][0]
    assert coords[0] == coords[-1]
    # 5 km x 5 km square = 2,500 ha, below the documented 3,000 ha maximum.
    lat_span = max(p[1] for p in coords) - min(p[1] for p in coords)
    assert 0.044 < lat_span < 0.046
    calls = route(monkeypatch, lambda m, u, p: Resp([{"id": "existing", "name": agro.study_polygon_name("Accra")}]))
    poly = agro.find_or_create_study_polygon("Accra", 5.618, -0.171)
    assert poly["id"] == "existing" and len(calls) == 1


def test_satellite_search_request_and_scene_sort(monkeypatch):
    calls = route(monkeypatch, lambda m, u, p: Resp([
        {"dt": 1704153600, "image": {"ndvi": "https://api.agromonitoring.com/image/1.0/a/b?appid=secret"}},
        {"dt": 1704067200, "image": {"truecolor": "https://api.agromonitoring.com/image/1.0/c/d?appid=secret"}},
        {"dt": 1704000000},
    ]))
    scenes = agro.search_satellite_images("poly1", 1704000000, 1705000000)
    assert [s["dt"] for s in scenes] == [1704153600, 1704067200]
    assert calls[0]["url"].endswith("/agro/1.0/image/search")
    assert calls[0]["params"]["polyid"] == "poly1" and calls[0]["params"]["start"] == 1704000000


def test_satellite_image_fetch_is_server_side_and_host_restricted(monkeypatch):
    class ImageResponse:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = b"\\x89PNG\\r\\n"
    calls = []
    monkeypatch.setattr(agro.requests, "get", lambda url, timeout: (calls.append(url) or ImageResponse()))
    scene = {"image": {"ndvi": "https://api.agromonitoring.com/image/1.0/a/b?appid=secret"}}
    assert agro.fetch_satellite_image(scene, "ndvi") == ImageResponse.content
    assert len(calls) == 1 and "appid=secret" in calls[0]
    with pytest.raises(ValueError, match="unexpected product host"):
        agro.fetch_satellite_image({"image": {"ndvi": "https://evil.example/image?appid=secret"}}, "ndvi")
    with pytest.raises(ValueError, match="not available"):
        agro.fetch_satellite_image({"image": {}}, "ndvi")


def test_satellite_stats_fetch_and_invalid_json(monkeypatch):
    class StatsResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def json(self):
            return {"mean": 0.62, "median": 0.64}
    monkeypatch.setattr(agro.requests, "get", lambda url, timeout: StatsResponse())
    scene = {"stats": {"ndvi": "https://api.agromonitoring.com/stats/1.0/a/b?appid=secret"}}
    assert agro.fetch_satellite_stats(scene, "ndvi")["mean"] == 0.62
    assert agro.fetch_satellite_stats({"stats": {}}, "ndvi") is None
