"""Smoke and safety tests for run_analysis, make_figures and make_reports. Synthetic data only, in a temp folder."""
import json

import pandas as pd
import pytest

from earthscope import config
from earthscope.ingest import pipeline
from scripts import make_figures, make_reports, run_analysis, validate_power_files
from tests import synthetic

NAME = "POWER_Point_Monthly_19810101_20251231_005d62N_000d17W_LST_Accra.json"


@pytest.fixture
def synth(tmp_path, monkeypatch):
    monkeypatch.setenv("EARTHSCOPE_DATA_DIR", str(tmp_path / "data"))
    locs = {"Accra": (5.618, -0.171), "Kumasi": (6.695, -1.616)}
    names = {"Accra": "POWER_Point_Monthly_19810101_20251231_005d62N_000d17W_LST_Accra.json",
             "Kumasi": "POWER_Point_Monthly_19810101_20251231_006d70N_001d62W_LST_Kumasi.json"}
    for i, (loc, (la, lo)) in enumerate(locs.items()):
        (tmp_path / names[loc]).write_text(json.dumps(synthetic.make_power_like(la, lo, 1981, 2025, seed=i)))
    out = tmp_path / "rep"
    assert validate_power_files.main([str(tmp_path), "--out-dir", str(out)]) == 0
    pipeline.import_files(sorted(tmp_path.glob("POWER_Point_*.json")))
    pipeline.build_processed(locations=locs)
    return tmp_path, out


def test_analysis_refuses_synthetic_data_by_default(synth):
    _, out = synth
    assert run_analysis.main(["--out-dir", str(out)]) == 1
    assert not (out / "tables").exists() or not list((out / "tables").glob("trend_results_primary.csv"))


def test_analysis_figures_and_reports_pipeline_runs_on_labelled_synthetic_data(synth):
    _, out = synth
    assert run_analysis.main(["--out-dir", str(out), "--allow-synthetic"]) == 0
    t = pd.read_csv(out / "tables" / "trend_results_primary.csv")
    assert len(t) == 14 and set(t.fdr_family) == {"primary", "secondary_solar"} and (t.source == "SYNTHETIC TEST DATA").all()
    for name in ("qc_coverage_missingness", "qc_homogeneity_pettitt", "sensitivity_robustness", "climatology_1991_2020", "qc_duplicates"):
        assert (out / "tables" / f"{name}.csv").exists()
    run = json.loads((out / "analysis_run.json").read_text())
    assert run["synthetic_data"] is True and len(run["input_sha256"]) == 64
    assert make_figures.main(["--out-dir", str(out)]) == 0
    assert (out / "figures" / "trend_summary_forest.png").stat().st_size > 10_000
    assert make_reports.main(["--out-dir", str(out)]) == 1                       # reports are never written for synthetic data
    assert not (out / "TREND_ANALYSIS_REPORT.md").exists()


def test_report_text_never_contains_em_or_en_dashes_in_the_real_reports():
    real = config.ROOT / "reports"
    for f in real.glob("*.md"):
        txt = f.read_text()
        assert "\u2014" not in txt and "\u2013" not in txt, f.name
