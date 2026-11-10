"""Ingest, units, provenance and QC tests. Synthetic inputs only."""
import json

import numpy as np
import pytest

from earthscope import config
from earthscope.ingest import pipeline, power
from earthscope.qc import checks
from tests import synthetic


@pytest.fixture
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("EARTHSCOPE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def meta():
    return json.loads((config.processed_dir() / pipeline.METADATA_NAME).read_text())


# ---------------------------------------------------------------- URLs and parsing
def test_url_matches_power_api_shape():
    u = power.build_url(5.6, -0.19, 1981, 2025)
    assert "monthly/point" in u and "WS10M" in u and "start=1981&end=2025" in u and "format=JSON" in u


def test_json_parser_fill_annual_units_and_columns():
    p = synthetic.make_payload(5.6, -0.19, 2000, 2001, missing=[("T2M", "200003")])
    df = power.parse_json(p, "Accra")
    assert not df["date"].dt.month.eq(13).any()
    assert df[df.variable == "T2M"]["value"].isna().sum() == 1
    assert set(df["unit"]) == {"C", "mm/day", "%", "m/s"} and (df["unit_source"] == "response_metadata").all()
    assert list(df.columns) == power.STANDARD_COLUMNS


def test_csv_parser_matches_layout_and_units():
    df = power.parse_csv(synthetic.make_csv(5.6, -0.19, 1990, 1992), "Accra")
    assert set(df["variable"]) == {"T2M", "PRECTOTCORR"} and len(df) == 2 * 3 * 12
    assert set(df["unit"]) == {"C", "mm/day"} and df["latitude"].iat[0] == 5.6


def test_bad_json_rejected():
    with pytest.raises(ValueError):
        power.parse_json({"hello": 1}, "Accra", 5.6, -0.19)


# ---------------------------------------------------------------- units and metadata
def test_missing_units_metadata_is_rejected():
    p = synthetic.make_payload(5.6, -0.19, 2000, 2002, units=None)
    with pytest.raises(power.UnitError, match="no units"):
        power.parse_json(p, "Accra")


def test_wrong_units_are_rejected_not_converted():
    p = synthetic.make_payload(5.6, -0.19, 2000, 2002, units={"T2M": "K", "PRECTOTCORR": "mm/day", "RH2M": "%", "WS10M": "m/s"})
    with pytest.raises(power.UnitError, match="Nothing is converted"):          # Kelvin: not a known spelling
        power.parse_json(p, "Accra")
    p = synthetic.make_payload(5.6, -0.19, 2000, 2002, units={"T2M": "C", "PRECTOTCORR": "mm/month", "RH2M": "%", "WS10M": "m/s"})
    with pytest.raises(power.UnitError):                                         # monthly total, not a daily rate
        power.parse_json(p, "Accra")
    p = synthetic.make_payload(5.6, -0.19, 2000, 2002, units={"T2M": "%", "PRECTOTCORR": "mm/day", "RH2M": "%", "WS10M": "m/s"})
    with pytest.raises(power.UnitError, match="differs from the expected"):    # recognised but wrong for T2M
        power.parse_json(p, "Accra")


def test_unrecognised_unit_string_is_rejected():
    p = synthetic.make_payload(5.6, -0.19, 2000, 2002, units={"T2M": "furlongs", "PRECTOTCORR": "mm/day", "RH2M": "%", "WS10M": "m/s"})
    with pytest.raises(power.UnitError, match="unrecognised"):
        power.parse_json(p, "Accra")


def test_unit_spelling_aliases_are_accepted_and_normalised():
    u = {"T2M": "\u00b0C", "PRECTOTCORR": "mm day-1", "RH2M": "percent", "WS10M": "m s-1"}
    df = power.parse_json(synthetic.make_payload(5.6, -0.19, 2000, 2002, units=u), "Accra")
    assert set(df["unit"]) == {"C", "mm/day", "%", "m/s"}


def test_assume_documented_units_is_explicit_and_recorded(datadir):
    f = synthetic.write_json(datadir / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990, units=None)
    raw = config.raw_dir()
    (raw / f.name).write_text(f.read_text())
    with pytest.raises(power.UnitError):
        pipeline.build_processed()
    df = pipeline.build_processed(assume_documented_units=True)
    assert (df["unit_source"] == "assumed_documented_default").all()
    assert meta()["assumed_documented_units_used"] is True


def test_statistic_column_separates_mean_max_min_and_precip_rate():
    assert power.statistic_for("T2M") == "monthly_mean_of_daily_mean"
    assert power.statistic_for("T2M_MAX") == "monthly_maximum_of_hourly_values"
    assert power.statistic_for("T2M_MIN") == "monthly_minimum_of_hourly_values"
    assert "not_a_monthly_total" in power.statistic_for("PRECTOTCORR")
    assert power.statistic_for("SOMETHING_NEW") == "unknown"


# ---------------------------------------------------------------- provenance sidecar
def test_parameter_metadata_is_preserved_verbatim_and_resolution_not_invented(datadir):
    pm = {"T2M": {"source": "MERRA-2 (as stated by the response)", "definition": "kept verbatim"}}
    synthetic.write_json(config.raw_dir() / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990, param_meta=pm)
    pipeline.build_processed()
    v = meta()["variables"]
    assert v["T2M"]["response_parameter_metadata_verbatim"]["source"] == "MERRA-2 (as stated by the response)"
    assert v["T2M"]["response_parameter_metadata_verbatim"]["units"] == "C"
    assert all(x["spatial_resolution"] == "not stated in the response; not verified" for x in v.values())
    assert v["T2M"]["semantics_status"] == config.SEMANTICS_STATUS


def test_resolution_is_recorded_only_when_the_response_states_it(datadir):
    synthetic.write_json(config.raw_dir() / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990,
                         header_extra={"spatial_resolution": "0.5 x 0.625 degree (stated by test fixture)"})
    pipeline.build_processed()
    assert meta()["variables"]["T2M"]["spatial_resolution"].startswith("0.5 x 0.625")


def test_actual_coverage_differs_from_requested_and_is_recorded(datadir):
    p = synthetic.make_payload(5.6, -0.19, 1981, 2020, header_extra={"end": 2025},
                               missing=[("T2M", f"{y}{m:02d}") for y in (2019, 2020) for m in range(1, 13)])
    (config.raw_dir() / "power_monthly_Accra_1981_2020.json").write_text(json.dumps(p))
    pipeline.build_processed()
    f = meta()["files"][0]
    assert f["requested_end"] == 2025
    c = f["actual_coverage"]["T2M"]
    assert c["last_month_present"] == "2020-12-01" and c["last_valid_month"] == "2018-12-01"
    assert c["n_missing_values"] == 24 and c["first_valid_month"] == "1981-01-01"
    assert len(f["sha256"]) == 64


def test_fetch_record_is_attached_when_present(datadir):
    raw = config.raw_dir()
    name = "power_monthly_Accra_1981_1990.json"
    synthetic.write_json(raw / name, 5.6, -0.19, 1981, 1990)
    (raw / (name + pipeline.FETCH_SUFFIX)).write_text(json.dumps({"request_url": "u", "retrieved_utc": "t"}))
    pipeline.build_processed()
    assert meta()["files"][0]["fetch_record"]["request_url"] == "u"


# ---------------------------------------------------------------- QC
def test_qc_flags_missing_and_out_of_range_and_keeps_values():
    p = synthetic.make_payload(5.6, -0.19, 2000, 2001, missing=[("T2M", "200003")], bad=[("RH2M", "200004", 140.0)])
    df = checks.add_qc_flag(power.parse_json(p, "Accra"))
    assert (df.qc_flag == "missing").sum() == 1 and (df.qc_flag == "out_of_range").sum() == 1
    assert df.loc[df.qc_flag == "out_of_range", "value"].iat[0] == 140.0


def test_gaps_counts_absent_months_inside_the_span():
    p = synthetic.make_payload(5.6, -0.19, 2000, 2004, drop_months=[(2002, 3), (2002, 4)], drop_years=[2003])
    g = checks.gaps(power.parse_json(p, "Accra"))
    assert (g[g.variable == "T2M"]["absent_months"] == 14).all()


# ---------------------------------------------------------------- import, duplicates, overlaps
def test_import_json_and_csv_and_build(datadir):
    f1 = synthetic.write_json(datadir / "download_a.json", 5.6, -0.19, 1981, 2000)
    f2 = datadir / "whatever.csv"
    f2.write_text(synthetic.make_csv(6.69, -1.62, 1981, 2000))
    copied = pipeline.import_files([f1, f2])
    assert {c.name for c in copied} == {"power_monthly_Accra_1981_2000.json", "power_monthly_Kumasi_1981_2000.csv"}
    df = pipeline.build_processed()
    assert set(df["location"]) == {"Accra", "Kumasi"} and "qc_flag" in df
    assert meta()["rows"] == len(df)


def test_import_rejects_wrong_location_and_far_points(datadir):
    f = synthetic.write_json(datadir / "x.json", 10.06, -2.51, 1981, 1990)
    with pytest.raises(ValueError, match="do not match"):
        pipeline.import_files([f], location="Accra")
    f = synthetic.write_json(datadir / "y.json", 40.0, 10.0, 1981, 1990)
    with pytest.raises(ValueError, match="not near any configured"):
        pipeline.import_files([f])


def test_importing_from_the_raw_folder_itself_does_not_crash(datadir):
    raw = config.raw_dir()
    synthetic.write_json(raw / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990)
    assert len(pipeline.import_files([raw / "power_monthly_Accra_1981_1990.json"])) == 1


def test_duplicate_identical_rows_are_collapsed_and_counted(datadir):
    (config.raw_dir() / "power_monthly_Accra_1981_1990.csv").write_text(
        synthetic.make_csv(5.6, -0.19, 1981, 1990, dup_rows=[("T2M", 1985, 0.0)]))
    df = pipeline.build_processed()
    assert not df.duplicated(["location", "variable", "date"]).any()
    assert meta()["duplicates_removed"] == 12


def test_duplicate_conflicting_rows_in_one_file_are_an_error(datadir):
    (config.raw_dir() / "power_monthly_Accra_1981_1990.csv").write_text(
        synthetic.make_csv(5.6, -0.19, 1981, 1990, dup_rows=[("T2M", 1985, 0.5)]))
    with pytest.raises(ValueError, match="conflicting"):
        pipeline.build_processed()


def test_conflicting_overlapping_downloads_are_an_error(datadir):
    raw = config.raw_dir()
    synthetic.write_json(raw / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990, seed=1)
    synthetic.write_json(raw / "power_monthly_Accra_1985_1995.json", 5.6, -0.19, 1985, 1995, seed=2)
    with pytest.raises(ValueError, match="conflicting"):
        pipeline.build_processed()


def test_identical_overlap_is_merged(datadir):
    raw = config.raw_dir()
    synthetic.write_json(raw / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990, seed=1)
    synthetic.write_json(raw / "power_monthly_Accra_1981_1995.json", 5.6, -0.19, 1981, 1995, seed=1)
    df = pipeline.build_processed()
    assert not df.duplicated(["location", "variable", "date"]).any() and meta()["duplicates_removed"] > 0


def test_value_vs_missing_overlap_is_a_conflict(datadir):
    raw = config.raw_dir()
    synthetic.write_json(raw / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990, seed=1)
    synthetic.write_json(raw / "power_monthly_Accra_1981_1995.json", 5.6, -0.19, 1981, 1995, seed=1,
                         missing=[("T2M", "198505")])
    with pytest.raises(ValueError, match="conflicting"):
        pipeline.build_processed()


def test_units_differing_between_files_are_an_error(datadir):
    raw = config.raw_dir()
    synthetic.write_json(raw / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990)
    synthetic.write_json(raw / "power_monthly_Kumasi_1981_1990.json", 6.69, -1.62, 1981, 1990, units=None)
    with pytest.raises(power.UnitError):
        pipeline.build_processed()
    # assume flag would silently align them to the documented unit; that is allowed only explicitly
    df = pipeline.build_processed(assume_documented_units=True)
    assert set(df["unit_source"]) == {"response_metadata", "assumed_documented_default"}


# ---------------------------------------------------------------- synthetic identification
def test_synthetic_data_is_labelled_and_real_looking_data_is_not():
    syn = power.parse_json(synthetic.make_payload(5.6, -0.19, 2000, 2002), "Accra")
    assert (syn.source == "SYNTHETIC TEST DATA").all() and (syn.data_kind == "synthetic_test").all()
    real = power.parse_json(synthetic.make_payload(5.6, -0.19, 2000, 2002, real_looking=True), "Accra")
    assert (real.source == "NASA POWER").all() and (real.data_kind == "gridded_estimate_not_station_observation").all()


def test_synthetic_label_reaches_the_metadata_file(datadir):
    synthetic.write_json(config.raw_dir() / "power_monthly_Accra_1981_1990.json", 5.6, -0.19, 1981, 1990)
    pipeline.build_processed()
    assert "SYNTHETIC TEST DATA" in meta()["sources"] and "synthetic_test" in meta()["data_kind"]
