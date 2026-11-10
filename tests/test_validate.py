"""Pre-import validator tests. Synthetic fixtures only (laid out like real POWER responses)."""
import copy
import json

import pytest

from earthscope import config
from earthscope.ingest import pipeline, power, validate
from scripts import validate_power_files
from tests import synthetic

NAME = "POWER_Point_Monthly_19810101_20201231_005d60N_000d19W_LST_Accra.json"


@pytest.fixture
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("EARTHSCOPE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def write(tmp, payload, name=NAME):
    p = tmp / name
    p.write_text(json.dumps(payload))
    return p


def status(res, check):
    return next(c["status"] for c in res["checks"] if c["check"] == check)


def good():
    return synthetic.make_power_like(5.6, -0.19)


def test_clean_file_passes_every_check(tmp_path):
    r = validate.validate_file(write(tmp_path, good()))
    assert r["status"] == "pass", [c for c in r["checks"] if c["status"] in ("fail", "warn")]
    assert r["location_identity"]["nearest_configured_location"] == "Accra"
    assert all(v["annual_value_consistent_with_documented_statistic"] for k, v in r["semantics_evidence"].items() if "test" in v)
    assert r["semantics_evidence"]["ordering_Tmax_ge_T_ge_Tmin"]["violations"] == 0
    assert len(r["sha256"]) == 64


def test_not_a_power_file(tmp_path):
    assert validate.validate_file(write(tmp_path, {"hello": 1}))["status"] == "fail"
    p = tmp_path / "x.json"
    p.write_text("{not json")
    assert validate.validate_file(p)["status"] == "fail"


def test_duplicate_keys_are_detected(tmp_path):
    p = tmp_path / NAME
    text = json.dumps(good()).replace('"198101": ', '"198101": 1.0, "198101": ', 1)
    p.write_text(text)
    r = validate.validate_file(p)
    assert status(r, "no_duplicate_keys") == "fail"


def test_units_missing_or_wrong_fail(tmp_path):
    d = good(); d["parameters"]["T2M"]["units"] = "K"
    assert status(validate.validate_file(write(tmp_path, d)), "units_T2M") == "fail"
    d = good(); del d["parameters"]["RH2M"]["units"]
    r = validate.validate_file(write(tmp_path, d))
    assert status(r, "every_parameter_has_units_metadata") == "fail" and status(r, "units_RH2M") == "fail"
    d = good(); d["parameters"]["PRECTOTCORR"]["units"] = "mm/month"
    assert status(validate.validate_file(write(tmp_path, d)), "units_PRECTOTCORR") == "fail"


def test_missing_requested_parameter_fails_and_extra_is_reported(tmp_path):
    d = good(); del d["properties"]["parameter"]["RH2M"]; del d["parameters"]["RH2M"]
    assert status(validate.validate_file(write(tmp_path, d)), "all_requested_parameters_returned") == "fail"
    r = validate.validate_file(write(tmp_path, good()), requested=["T2M", "T2M_MAX"])
    assert status(r, "extra_parameters_returned") == "info"


def test_returned_range_shorter_than_requested_is_not_assumed_complete(tmp_path):
    r = validate.validate_file(write(tmp_path, synthetic.make_power_like(5.6, -0.19, 1981, 2020, header_end=2025)))
    assert status(r, "returned_keys_cover_the_requested_header_range") == "fail"
    c = [x for x in r["checks"] if x["check"] == "returned_keys_cover_the_requested_header_range"][0]
    assert c["last_returned"] == "202013" and r["coverage"]["T2M"]["n_absent_keys_vs_header_range"] == 5 * 12


def test_fill_values_and_absent_months_are_counted(tmp_path):
    d = good()
    for y in (1981, 1982):
        for m in range(1, 13):
            d["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"][f"{y}{m:02d}"] = -999
    for k in ("200005", "200006"):
        for v in d["properties"]["parameter"]:
            del d["properties"]["parameter"][v][k]
    r = validate.validate_file(write(tmp_path, d))
    c = r["coverage"]["ALLSKY_SFC_SW_DWN"]
    assert c["n_fill_values"] == 24 and c["first_fill_key"] == "198101" and c["last_fill_key"] == "198212"
    assert c["years_with_any_fill"] == [1981, 1982] and c["first_valid"] == "198301"
    assert r["coverage"]["T2M"]["n_absent_keys_vs_header_range"] == 2 and status(r, "coverage_T2M") == "warn"


def test_out_of_range_and_ordering_violations_fail(tmp_path):
    d = good(); d["properties"]["parameter"]["RH2M"]["199001"] = 140.0
    assert status(validate.validate_file(write(tmp_path, d)), "values_within_physical_limits_RH2M") == "fail"
    d = good(); d["properties"]["parameter"]["T2M_MAX"]["199001"] = 10.0
    assert status(validate.validate_file(write(tmp_path, d)), "T2M_MAX_ge_T2M_ge_T2M_MIN_every_month") == "fail"


def test_semantics_evidence_distinguishes_extremes_from_means(tmp_path):
    d = good()
    # make annual T2M_MAX the MEAN of the months instead of the maximum: the documented definition no longer fits
    s = d["properties"]["parameter"]["T2M_MAX"]
    for y in range(1981, 2021):
        s[f"{y}13"] = sum(s[f"{y}{m:02d}"] for m in range(1, 13)) / 12
    r = validate.validate_file(write(tmp_path, d))
    assert status(r, "annual_value_consistent_with_T2M_MAX_definition") == "warn"
    assert r["semantics_evidence"]["T2M_MAX"]["max_abs_diff_simple"] < 1e-9
    d = good(); d["properties"]["parameter"]["T2M"]["199013"] += 0.5
    assert status(validate.validate_file(write(tmp_path, d)), "annual_value_consistent_with_T2M_definition") == "warn"
    # the real convention: annual mean equals the day-weighted mean but NOT the simple mean of the months
    ev = validate.validate_file(write(tmp_path, good()))["semantics_evidence"]["T2M"]
    assert ev["max_abs_diff_weighted"] <= validate.ROUNDING_TOL and ev["max_abs_diff_simple"] > validate.ROUNDING_TOL


def test_coordinates_and_location_identity(tmp_path):
    bad_name = "POWER_Point_Monthly_19810101_20201231_009d41N_000d84W_LST_Tamale.json"      # name says Tamale, file is Accra
    r = validate.validate_file(write(tmp_path, good(), bad_name))
    assert status(r, "filename_coordinates_match_file_coordinates") == "fail"
    assert status(r, "named_location_is_the_nearest_configured_location") == "fail"
    wa = "POWER_Point_Monthly_19810101_20201231_005d60N_000d19W_LST_Wa.json"                  # coordinates agree, name is wrong place
    r = validate.validate_file(write(tmp_path, good(), wa))
    assert status(r, "named_location_is_the_nearest_configured_location") == "fail"
    r = validate.validate_file(write(tmp_path, good(), "download.json"))
    assert status(r, "location_can_be_identified") == "warn"
    assert validate.haversine_km(5.6, -0.19, 5.6, -0.19) == 0
    assert 110 < validate.haversine_km(0, 0, 1, 0) < 112


def test_compare_files_flags_real_differences_and_ignores_order_only_differences():
    a = good(); b = synthetic.make_power_like(6.69, -1.62, seed=1, sources=["SRB", "SYN1DEG", "MERRA2", "POWER"])
    out = validate.compare_files({"a": a, "b": b})
    assert out["header_sources_identical_as_sets"] and not out["header_sources_identical_in_order"]
    assert out["header_identical_except_sources"] and out["parameters_metadata_identical"] and out["coordinates_all_distinct"]
    assert out["pairs_with_mostly_identical_series"] == []
    c = copy.deepcopy(a)
    c["geometry"]["coordinates"] = [-1.0, 7.0, 100.0]
    same = validate.compare_files({"a": a, "c": c})
    assert {"a", "c"} == set(same["pairs_with_mostly_identical_series"][0]["pair"])        # identical values at two points: same grid cell?
    d = copy.deepcopy(b); d["parameters"]["T2M"]["units"] = "K"
    assert not validate.compare_files({"a": a, "d": d})["parameters_metadata_identical"]


def test_script_writes_report_and_sets_exit_code(tmp_path):
    write(tmp_path, good())
    out = tmp_path / "rep"
    assert validate_power_files.main([str(tmp_path / NAME), "--out-dir", str(out)]) == 0
    rep = json.loads((out / "preimport_validation.json").read_text())
    assert rep["files"][0]["status"] == "pass"
    bad = good(); bad["parameters"]["T2M"]["units"] = "K"
    write(tmp_path, bad, "POWER_Point_Monthly_19810101_20201231_005d60N_000d19W_LST_Bad.json")
    assert validate_power_files.main([str(tmp_path / "POWER_Point_Monthly_19810101_20201231_005d60N_000d19W_LST_Bad.json"),
                                      "--out-dir", str(out)]) == 1


# ---------------------------------------------------------------- viewer file names and import records
def test_viewer_filename_is_parsed():
    f = power.parse_viewer_filename("POWER_Point_Monthly_19810101_20251231_005d62N_000d17W_LST_Accra.json")
    assert f == {"location": "Accra", "latitude": 5.62, "longitude": -0.17, "start": "19810101", "end": "20251231",
                 "time_standard": "LST", "format": "json"}
    assert power.parse_viewer_filename("POWER_Point_Monthly_19810101_20251231_004d90S_001d76E_UTC_X.json")["latitude"] == -4.9
    assert power.parse_viewer_filename("random.json") is None


def test_import_identifies_location_records_original_name_and_new_metadata(datadir):
    src = write(datadir, good())
    copied = pipeline.import_files([src])
    assert copied[0].name == "power_monthly_Accra_1981_2020.json"
    rec = json.loads((copied[0].parent / (copied[0].name + pipeline.IMPORT_SUFFIX)).read_text())
    assert rec["original_filename"] == NAME and len(rec["original_sha256"]) == 64 and "viewer" in rec["location_identified_from"]
    pipeline.build_processed()
    f = json.loads((config.processed_dir() / pipeline.METADATA_NAME).read_text())["files"][0]
    assert f["import_record"]["original_filename"] == NAME and f["time_standard"] == "LST"
    assert f["header_sources_sorted"] == ["MERRA2", "POWER", "SRB", "SYN1DEG"] and f["elevation_value_in_file_m"] == 27.76


def test_import_refuses_filename_that_disagrees_with_file_content(datadir):
    bad = "POWER_Point_Monthly_19810101_20201231_009d41N_000d84W_LST_Tamale.json"
    with pytest.raises(ValueError, match="coordinates in the file name"):
        pipeline.import_files([write(datadir, good(), bad)])


def test_extra_solar_parameter_is_imported_with_its_own_unit(datadir):
    pipeline.import_files([write(datadir, good())])
    df = pipeline.build_processed()
    s = df[df.variable == "ALLSKY_SFC_SW_DWN"]
    assert (s.unit == "kW-hr/m^2/day").all() and (s.unit_source == "response_metadata").all()
    assert (df.data_kind == "synthetic_test").all()
