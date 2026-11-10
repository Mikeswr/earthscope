import pytest
from streamlit.testing.v1 import AppTest

from earthscope import config
from earthscope.ingest import pipeline
from tests import synthetic

from pathlib import Path
APP = str(Path(__file__).resolve().parents[1] / "earthscope" / "dashboard" / "app.py")


@pytest.fixture
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("EARTHSCOPE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def test_empty_state_shows_instructions_and_no_charts(datadir):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("No data loaded" in i.value for i in at.info)
    assert len(at.tabs) == 0


def test_synthetic_data_renders_with_warning(datadir):
    raw = config.raw_dir()
    synthetic.write_json(raw / "power_monthly_Accra_1981_2020.json", 5.6, -0.19, 1981, 2020, seed=1)
    synthetic.write_json(raw / "power_monthly_Tamale_1981_2020.json", 9.4, -0.84, 1981, 2020, 0.0, 2)
    pipeline.build_processed()
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("SYNTHETIC TEST DATA" in e.value for e in at.error)
    assert len(at.tabs) == 6
    for var in ["PRECTOTCORR", "RH2M", "T2M", "WS10M"]:
        at.sidebar.selectbox[1].select(var).run()
        assert not at.exception, [e.value for e in at.exception]
    at.sidebar.selectbox[0].select("Tamale").run()
    assert not at.exception


def test_short_record_shows_reason_instead_of_a_number(datadir):
    synthetic.write_json(config.raw_dir() / "power_monthly_Accra_2015_2019.json", 5.6, -0.19, 2015, 2019)
    pipeline.build_processed()
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("No annual trend reported" in w.value for w in at.warning)
