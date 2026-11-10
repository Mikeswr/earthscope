EarthScope

Environmental trend analysis for Ghana from NASA POWER monthly data, with a Streamlit dashboard. NASA POWER values are gridded estimates built from reanalysis and satellite based sources. They are not direct station observations, and five locations are five separate series, not a spatial trend map.

Setup
1. python -m venv .venv and activate it
2. pip install -r requirements.txt
3. OpenWeather current conditions require OPENWEATHER_API_KEY. In Streamlit Community Cloud, add it under App settings → Secrets as OPENWEATHER_API_KEY = "your_api_key". Locally, set it as an environment variable or in .env. Never commit or share API keys. Agromonitoring credentials are only needed for its separate client.

Workflow with downloaded NASA POWER files (details in docs/MANUAL_DOWNLOAD.md)
1. python scripts/validate_power_files.py <folder>      checks the files, changes nothing
2. python scripts/import_power.py <folder>              imports, refuses unit, identity or overlap problems
3. python scripts/run_analysis.py                       QC tables, trends, sensitivity runs, comparison tables
4. python scripts/make_figures.py                       figures
5. python scripts/make_reports.py                       four markdown reports from the tables
6. streamlit run dashboard/app.py            dashboard
With internet access, scripts/fetch_power.py downloads the files itself. scripts/inspect_file.py prints a file's structure without values.

Outputs
data/raw                      imported files, each with an .import.json record (original name, checksum)
data/processed                standardised table, metadata with checksums and coverage, trend_results.csv, anomalies.csv
reports/                      IMPORT_AND_DATA_QUALITY_REPORT.md, TREND_ANALYSIS_REPORT.md, LOCATION_COMPARISON_TABLES.md, LIMITATIONS_AND_FURTHER_VALIDATION.md, preimport_validation.json, analysis_run.json
reports/tables, reports/figures   every table as CSV, and the figures

Method summary (details and limits in docs/METHODS.md)
Units come from the response metadata and mismatches are rejected. Flagged and missing values stay in the data as NaN at their calendar position and are excluded from statistics; nothing is interpolated. Annual values: day-weighted mean, annual maximum for T2M_MAX, annual minimum for T2M_MIN, all 12 months required. Sen's slope and the tests use real elapsed years, and coverage rules count flagged years at the start, middle and end. Annual Mann-Kendall inflates its variance for lag-1 autocorrelation. FDR is applied within pre-declared families, and uncorrected and corrected significance are always shown together with one evidence class per series. The seasonal test is not used for significance. Each test has documented minimum data and reports a reason when it is not met.

Tests
python -m pytest
The tests use synthetic data labelled SYNTHETIC TEST DATA. If such data is ever loaded, the dashboard shows a red warning, the label follows the data into every output, and run_analysis.py and make_reports.py refuse it.

Status
Done and run on the five real NASA POWER files: validation, import, QC, trend analysis, sensitivity runs, figures, reports.
Not verified: agreement of POWER values with station records; live OpenWeather and Agromonitoring responses. The dashboard now has a separate OpenWeather current-conditions panel, but it requires the user's API key and has not yet been tested against that live account. OpenWeather current conditions are not included in NASA POWER trend calculations. Historical OpenWeather integration remains gated on confirming endpoint entitlement and live response structure.
Not built: a covariance corrected seasonal test, gridded spatial trend maps (needs gridded input), deployment, Space Apps submission materials.
