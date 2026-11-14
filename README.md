# EarthScope

**A geospatial intelligence platform for exploring environmental trends in Ghana.**

EarthScope combines long-term climate analysis from NASA POWER with separate live weather monitoring panels from OpenWeather and Agromonitoring.

**Public dashboard:** https://earthscope.streamlit.app/  
**Repository:** https://github.com/Mikeswr/earthscope

## Who EarthScope is for

EarthScope is designed for two connected audiences:

- **The general public:** people who want to understand environmental change without needing a climate-science background. Plain-language explanations help visitors distinguish daily weather, natural variability and long-term trends.
- **People working with environmental evidence:** researchers, solar energy professionals, planners, policymakers and environmental organisations who need location-specific measurements, statistical evidence and transparent methods.

The platform presents the same underlying evidence to both audiences. Public-facing explanations make the results easier to understand, while the detailed methods, data-quality information and limitations remain available for technical review.

## A featured finding: surface solar energy at Accra

NASA POWER monthly gridded estimates indicate a statistically significant declining trend in estimated all-sky surface shortwave solar energy at the Accra grid point from 1984 to 2025. The estimated Sen's slope is **−0.0514 kWh/m²/day per decade** (95% confidence interval: **−0.0716 to −0.0285**; FDR-adjusted p-value: **0.0008**).

This is a finding about estimated solar energy reaching the surface. It is not a measurement of solar-panel electricity generation, does not establish the physical cause of the decline, and requires independent validation against ground-based radiation measurements. It is presented as a signal worth investigating for solar resource assessment and energy planning, not as a direct prediction of energy output.

## What it does

- Explore monthly environmental variables for Accra, Kumasi, Tamale, Wa and Takoradi.
- Examine the 1981–2025 NASA POWER record for seven variables: T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, RH2M, WS10M and ALLSKY_SFC_SW_DWN.
- Compare annual series, anomalies, quality-control flags, trend estimates and evidence classes.
- View point-level trend comparisons on a map.
- Explore a separate Future Outlook module with rolling-origin model comparison, monthly forecasts and empirical uncertainty bands.
- Check current weather through OpenWeather and Agromonitoring, with recent hourly history where the configured account permits it.
- Explore available Agromonitoring satellite scenes for selected study footprints, including true colour, false colour, NDVI, EVI, EVI2 and NDWI products where returned by the API.\n- Explore available Agromonitoring satellite scenes for selected study footprints, including true colour, false colour, NDVI, EVI, EVI2 and NDWI products where returned by the API.

## Data sources and interpretation

### NASA POWER

The climate-analysis dataset consists of monthly NASA POWER point/grid-cell estimates for five configured locations. These are gridded estimates based on satellite and model/reanalysis inputs, not direct station observations.

The five locations are five separate time series. They do **not** constitute a continuous spatial trend map and do not support claims about every location in Ghana.

### OpenWeather

The dashboard provides current conditions and a recent four-hour historical view. The recent hourly records are observations/history, not a forecast. Older historical archive access and One Call 3.0 timestamp history were not available under the tested account access.

Set OPENWEATHER_API_KEY in Streamlit Community Cloud secrets or as a local environment variable. Never commit API keys.

### Agromonitoring

The dashboard provides current weather and a recent hourly history view. A request for January 2020 returned HTTP 400, requested data is out of allowed range, under the tested account. Older weather archive access is therefore not claimed.

The Satellite imagery tab uses Agromonitoring's two-step imagery API: it prepares or reuses a named 25 km² square study polygon centred on the selected EarthScope coordinate, searches for available scenes, and retrieves the returned image products and vegetation-index statistics server-side. The footprint is an analytical square, not an official administrative boundary. Agromonitoring imagery coverage varies by place, acquisition date, cloud cover and account entitlement. No live satellite imagery endpoint is claimed verified until tested against the deployed key. Imagery and indices remain separate from NASA POWER trend calculations.

Set AGROMONITORING_API_KEY only if using this separate client. Keep its outputs separate from NASA POWER climate-trend calculations.

**Live weather data are not merged into the NASA POWER analysis.** Differences in source, temporal resolution, spatial support and access period mean they must be interpreted separately.

## Analysis workflow

With downloaded NASA POWER files:

1. python scripts/validate_power_files.py <folder> validates the files without importing them.
2. python scripts/import_power.py <folder> imports the files and builds the standardised dataset.
3. python scripts/run_analysis.py runs QC summaries, trend analysis, sensitivity runs and comparison tables.
4. python scripts/make_figures.py generates figures.
5. python scripts/make_reports.py generates Markdown reports from the analysis tables.
6. streamlit run dashboard/app.py launches the dashboard locally.

With internet access, scripts/fetch_power.py can download NASA POWER data. See the script help for options. The generated reports and tables are written to the selected output directory, which defaults to a local reports/ folder.

The detailed method specification is available in [METHODS.md](METHODS.md).\n\n## Statistical approach

- Missing and flagged observations remain at their original calendar positions as missing values. No interpolation is performed.
- Annual means are day-weighted from monthly values and require all 12 months. T2M_MAX and T2M_MIN use annual maxima and minima of the monthly extremes, respectively.
- Sen's slope uses actual elapsed years and is reported per decade.
- Annual Mann-Kendall variance uses a lag-1 autocorrelation effective-sample-size adjustment (ar1_neff) in the primary analysis. Hamed-Rao and no-correction results are included as sensitivity checks.
- Benjamini-Hochberg false-discovery-rate correction is applied within the declared primary and secondary variable families. Both uncorrected and adjusted p-values are retained.
- Seasonal Mann-Kendall results are calculated for diagnostics but are not used to make significance claims because between-month dependence is not corrected.
- Sensitivity runs examine alternative autocorrelation correction, FDR method, annual aggregation, common-period coverage and precipitation extremes.

## Future outlook

The dashboard includes an experimental statistical forecasting module for the selected NASA POWER location and variable. It compares seasonal-naive, linear trend plus calendar-month effects, and damped additive exponential-smoothing candidates using rolling-origin 12-month backtests. The candidate with the lowest pooled mean absolute error is selected. Approximate 80% and 95% empirical error bands are calibrated from withheld backtest errors and widened with forecast lead time. The forecast horizon is 1–5 years.

Forecasts require at least 10 years of consecutive valid monthly observations. Missing months are not interpolated. Forecast skill is reported against the seasonal-naive baseline. If a more complex model does not improve on the baseline, the dashboard says so. These are statistical extrapolations, not scenario-based climate projections. Their uncertainty bands do not capture future emissions, policy, land-use or climate-model scenario uncertainty. They must not be interpreted as guaranteed future conditions.

## Outputs\n\nThe repository includes the standardised monthly dataset, its provenance metadata, trend results and monthly anomaly table under data/processed/. The four narrative reports are stored at the repository root. The analysis scripts can regenerate report files and machine-readable tables in a local reports/ output directory. Raw NASA POWER downloads are not included in the repository.\n\n## Current status

**Implemented and previously run on the five supplied NASA POWER files:** file validation, import, quality control, trend analysis, sensitivity analysis, figures and report generation.

**Live dashboard:** publicly deployed. OpenWeather current conditions and four-hour history have been tested successfully. Agromonitoring current weather and recent hourly history have also been tested successfully. A January 2020 Agromonitoring archive request was rejected as outside the account's allowed range.

**Not yet independently validated:** agreement between NASA POWER estimates and ground station observations; the physical interpretation of the observed solar-radiation decline; precipitation extremes and change points.

**Not implemented:** continuous gridded spatial trend maps from a multi-year raster dataset; a dependence-corrected seasonal significance test; independent station validation; final Space Apps submission materials. Forecast skill and interval calibration have not yet been independently executed against the live dashboard dataset after this module was added.

## Reproducibility and tests

Run the automated suite with:

    python -m pytest

Synthetic fixtures are labelled SYNTHETIC TEST DATA. The analysis and report scripts refuse synthetic data by default, and the dashboard displays a warning if synthetic data are loaded.

Raw source files and API credentials should not be committed. Processed outputs retained in the repository must include their provenance metadata.