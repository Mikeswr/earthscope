"""The fetch script is tested with a fake HTTP layer. No network is used."""
import json

import pytest
import requests

from earthscope import config
from scripts import fetch_power
from tests import synthetic


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("EARTHSCOPE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(fetch_power.time, "sleep", lambda s: None)


class Resp:
    def __init__(self, payload=None, status=200):
        self.status_code, self.text = status, json.dumps(payload) if payload else "err"


def test_failure_writes_nothing_and_exits_1(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no network")
    monkeypatch.setattr(fetch_power.requests, "get", boom)
    code = fetch_power.main(["--locations", "Accra", "--end", "1990"])
    assert code == 1
    assert list(config.raw_dir().iterdir()) == [] and list(config.processed_dir().iterdir()) == []


def test_sidecar_record_is_written_next_to_each_raw_file(monkeypatch):
    monkeypatch.setattr(fetch_power.requests, "get", lambda url, timeout: Resp(synthetic.make_payload(5.6, -0.19, 1981, 1990)))
    assert fetch_power.main(["--locations", "Accra", "--end", "1990"]) == 0
    rec = json.loads((config.raw_dir() / "power_monthly_Accra_1981_1990.json.fetch.json").read_text())
    assert rec["http_status"] == 200 and "monthly/point" in rec["request_url"] and rec["retrieved_utc"]
    meta = json.loads((config.processed_dir() / "power_monthly_metadata.json").read_text())
    assert meta["files"][0]["fetch_record"]["requested"]["location"] == "Accra"


def test_valid_response_without_units_is_saved_but_processing_is_refused(monkeypatch):
    payload = synthetic.make_payload(5.6, -0.19, 1981, 1990, units=None)
    monkeypatch.setattr(fetch_power.requests, "get", lambda url, timeout: Resp(payload))
    assert fetch_power.main(["--locations", "Accra", "--end", "1990"]) == 3
    assert (config.raw_dir() / "power_monthly_Accra_1981_1990.json").exists()      # real data not thrown away
    assert not (config.processed_dir() / "power_monthly_standardised.csv").exists()


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(url, timeout):
        calls["n"] += 1
        return Resp(status=503) if calls["n"] < 3 else Resp(synthetic.make_payload(5.6, -0.19, 1981, 1990))
    monkeypatch.setattr(fetch_power.requests, "get", flaky)
    assert fetch_power.main(["--locations", "Accra", "--end", "1990"]) == 0
    assert calls["n"] == 3
    assert (config.raw_dir() / "power_monthly_Accra_1981_1990.json").exists()


def test_http_400_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def bad(url, timeout):
        calls["n"] += 1
        return Resp(status=400)
    monkeypatch.setattr(fetch_power.requests, "get", bad)
    assert fetch_power.main(["--locations", "Accra", "--end", "1990"]) == 1
    assert calls["n"] == 1


def test_partial_failure_keeps_good_data_and_reports(monkeypatch):
    acc_lat, acc_lon = config.load_locations()["Accra"]

    def pick(url, timeout):
        if f"latitude={acc_lat}&" in url:
            return Resp(synthetic.make_payload(acc_lat, acc_lon, 1981, 1990))
        raise requests.Timeout("slow")
    monkeypatch.setattr(fetch_power.requests, "get", pick)
    assert fetch_power.main(["--locations", "Accra", "Wa", "--end", "1990"]) == 1
    assert sorted(p.name for p in config.raw_dir().iterdir()) == [
        "power_monthly_Accra_1981_1990.json", "power_monthly_Accra_1981_1990.json.fetch.json"]
    assert (config.processed_dir() / "power_monthly_standardised.csv").exists()


def test_garbage_response_is_not_saved(monkeypatch):
    monkeypatch.setattr(fetch_power.requests, "get", lambda url, timeout: Resp({"nope": 1}))
    assert fetch_power.main(["--locations", "Accra", "--end", "1990"]) == 1
    assert list(config.raw_dir().iterdir()) == []


def test_print_urls_covers_all_five(capsys):
    assert fetch_power.main(["--print-urls", "--end", "2025"]) == 0
    out = capsys.readouterr().out
    assert all(n in out for n in ["Accra", "Kumasi", "Tamale", "Wa", "Takoradi"])
