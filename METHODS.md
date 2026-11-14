# EarthScope statistical methods

This document describes the methods implemented in the repository. It distinguishes the primary annual trend analysis from diagnostics and sensitivity analyses. It does not establish that NASA POWER estimates agree with local station observations.

## 1. Data and temporal support

The primary analysis uses monthly NASA POWER point/grid-cell estimates for five configured Ghana locations. Each location is analysed as a separate series. The data are not direct station measurements, and five points do not form a continuous spatial field.

Seven variables are retained: T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, RH2M, WS10M and ALLSKY_SFC_SW_DWN. Units are checked against the response metadata during import. Missing values and values flagged by quality control are not interpolated.

NASA POWER monthly records include an annual key in addition to monthly keys. The trend pipeline constructs annual values from the monthly series rather than using the annual key as an additional observation.

## 2. Quality control and annual aggregation

Quality-control flags include missing values and broad variable-specific physical-range checks. Flagged values remain in the calendar series as missing for statistical calculations. A complete regular monthly index is reconstructed between the first and last record so absent months and flagged months retain their original positions.

An annual value is calculated only when all 12 months are valid. T2M, RH2M, PRECTOTCORR, WS10M and ALLSKY_SFC_SW_DWN use a day-weighted mean of monthly values. T2M_MAX uses the maximum of the 12 monthly maxima, and T2M_MIN uses the minimum of the 12 monthly minima. These two variables therefore represent annual extremes of the monthly extreme values, not annual means of daily maxima or minima.

PRECTOTCORR is treated as a monthly mean daily precipitation rate in mm/day. It is not interpreted as a monthly accumulated rainfall total.

## 3. Trend magnitude

Trend magnitude is estimated using Sen's slope, the median of all pairwise slopes. The denominator uses the actual elapsed difference between observation years, so gaps are not treated as consecutive observations. Slopes are multiplied by ten and reported per decade.

## 4. Annual Mann-Kendall test

The primary monotonic-trend test is the two-sided Mann-Kendall test applied to annual values. The implementation includes the standard tie correction to the variance of the S statistic and uses the normal approximation for the test statistic.

The default minimum requirements are 10 valid annual observations and valid observations spanning at least 70 percent of the nominal year range. If either requirement is not met, the series is marked insufficient_data and no p-value is reported.

### Autocorrelation adjustment

The primary analysis uses an effective-sample-size variance inflation based on lag-1 autocorrelation of the Sen-detrended annual series. The estimated lag-1 correlation is computed only from pairs of consecutive calendar years that are both present. The implied AR(1) correlations are used to estimate a variance inflation factor, which is floored at 1 so this adjustment does not make the test less conservative than the unadjusted test.

This is an approximation, not a full model of temporal dependence. Its simulation checks in the test suite use synthetic AR(1) series and do not prove that the correction is calibrated for every climate series or for more complex persistence structures.

Hamed-Rao variance correction and no autocorrelation correction are retained as sensitivity scenarios. Their results are not substituted silently for the primary method.

## 5. Multiple testing

Benjamini-Hochberg false-discovery-rate adjustment is applied separately within the declared primary meteorological family and the secondary solar-radiation family. Both raw and adjusted p-values are retained. The evidence class distinguishes significant after FDR, significant before FDR only, not significant, and insufficient data.

Benjamini-Hochberg is justified under independence and certain positive-dependence conditions. Environmental variables and nearby locations can be correlated, so adjusted results should still be interpreted cautiously. The sensitivity analysis includes the more conservative Benjamini-Yekutieli procedure.

## 6. Seasonal Mann-Kendall diagnostic

A seasonal Mann-Kendall statistic is calculated by comparing observations within each calendar month across years, then summing the monthly statistics. The current implementation does not correct covariance between neighbouring months. Its p-values are retained for diagnostic purposes only and are not used for significance claims in the project findings.

A dependence-corrected seasonal significance procedure is not currently implemented.

## 7. Anomalies

Monthly anomalies are calculated relative to the same location and variable's calendar-month climatology over 1991–2020. A calendar month requires at least 20 valid values in the baseline period. Standardised anomaly scores use the baseline standard deviation, and the default flag threshold is an absolute z-score of at least 2.0.

## 8. Sensitivity analyses

The analysis script reruns the trend calculations under the following alternatives: no autocorrelation correction; Hamed-Rao correction; Benjamini-Yekutieli FDR; annual means instead of annual extremes for T2M_MAX and T2M_MIN; a common 1984–2025 period; and exclusion of selected high positive precipitation anomalies. The primary run retains the full input data and the configured annual aggregation.

These scenarios assess sensitivity to selected analytical choices. They are not independent replications and do not replace validation against independent observations.

## 9. Spatial analysis

The current dashboard map displays trend markers at the five configured locations. The spatial module contains a separate grid-trend function that accepts an annual raster cube with year, latitude and longitude coordinates. That function is not evidence that a gridded Ghana-wide trend analysis has been run. A continuous spatial analysis requires a suitable multi-year gridded dataset, documented spatial resolution, missing-data assessment and spatial multiple-testing treatment.

## 10. Interpretation limits

- NASA POWER values are gridded estimates, not direct station observations.
- The five configured locations do not support inference for all of Ghana.
- No independent station validation is currently reported.
- Precipitation extremes and solar-radiation trends require independent product checks.
- The annual autocorrelation adjustment is approximate.
- Seasonal p-values are not used for significance claims.
- Statistical significance does not establish a physical cause.

## 11. Experimental monthly forecasting

The dashboard's Future Outlook module provides statistical forecasts for an individual NASA POWER location-variable monthly series. It is deliberately separate from the historical Mann-Kendall trend analysis and from the live OpenWeather and Agromonitoring panels.

### Candidate methods

Three candidates are compared:

- Seasonal-naive: repeats the last observed 12-month seasonal cycle.
- Trend-seasonal regression: ordinary least squares linear time trend plus calendar-month fixed effects.
- Damped additive exponential smoothing: additive trend and additive 12-month seasonality with a damped trend component.

The selected candidate is the one with the lowest pooled mean absolute error across the rolling-origin backtests. The seasonal-naive method is retained as the required baseline. The dashboard reports MAE, RMSE, bias, number of withheld months, number of origins and skill relative to the baseline. A complex model is not described as an improvement if it does not beat the baseline.

### Backtesting and data requirements

The default evaluation uses five expanding-window origins, spaced 12 months apart. At each origin, the model is fitted only to observations available at that time and predicts the following 12 months. At least three valid origins are required. The training series must contain at least 120 consecutive valid monthly observations. Missing internal months cause forecasting to stop rather than being interpolated. Leading missing values are excluded, which permits the solar series to begin at its first valid month.

### Forecast intervals and horizon

The default forecast horizon is 24 months, with selectable horizons up to 60 months. Approximate 80% and 95% bands are calibrated from the empirical absolute errors of the selected model's withheld 12-month predictions. Band widths are expanded with the square root of lead time beyond 12 months. These are empirical statistical error bands, not formal probabilistic climate projection intervals. They assume that historical forecast errors remain informative and do not capture structural changes, future emissions, policy, land-use changes or climate-model scenario uncertainty.

Basic physical bounds are applied to precipitation, relative humidity, wind speed and downward shortwave radiation. Such clipping is a presentation safeguard and does not validate the forecast distribution.

### Interpretation and status

Forecasts are experimental outlooks for five NASA POWER grid-cell time series, not Ghana-wide climate projections. The model comparison and forecast outputs must be checked by running the automated tests and inspecting backtest diagnostics on the supplied real dataset before communicating any substantive future result. Forecasts are not mixed into the historical trend significance calculations. The current module does not use OpenWeather or Agromonitoring observations as training data.


## 12. Experimental compound hot-dry climate indicator

The regional analysis uses two monthly NASA POWER meteorological parameters on their returned native cell grid: T2M (2 m air temperature, °C) and PRECTOTCORR (bias-corrected precipitation rate, mm/day). The NASA POWER Monthly API documentation identifies the meteorological archive as MERRA-2 based from 1981 onward. Cell coordinates are preserved; no spatial interpolation or resampling is performed.

### Temperature anomaly

For each cell and calendar month, T2M is standardised relative to the 1991–2020 baseline:
`z_T = (T2M - monthly climatological mean) / monthly climatological standard deviation`.
At least 20 valid baseline values are required for each calendar month. The hot-condition threshold is `z_T >= +1.0`, indicating an unusually warm monthly mean relative to that cell's calendar-month baseline. It is not a daily heatwave definition.

### SPI-3 precipitation deficit

PRECTOTCORR is a monthly mean daily precipitation rate. It is converted to an approximate monthly accumulation by multiplying the rate by the number of calendar days in that month. A trailing three-month sum is then calculated; all three months must be valid.

For each ending calendar month, the 1991–2020 SPI-3 baseline values are fitted to a two-parameter gamma distribution with location fixed at zero. The empirical probability of zero precipitation is included as a zero-mass adjustment. The cumulative probability is transformed to a standard normal score. A minimum of 20 baseline values per ending calendar month is required. The dry-condition threshold is `SPI-3 <= -1.0`.

This follows the common SPI approach of fitting a probability distribution to accumulated precipitation and transforming its cumulative probability to the standard normal distribution. The exact fitting choices and baseline are recorded in the run metadata.

### Compound event and annual frequency

A month is classified as compound hot-dry only when both conditions are met in the same cell and month: `z_T >= +1.0` and `SPI-3 <= -1.0`. A month is unclassified when either input indicator is missing. Missing months are never converted to non-events.

Annual compound frequency is the percentage of classifiable months in that calendar year that meet both conditions. At least 9 classifiable months are required; otherwise the annual frequency remains missing.

### Spatial trend and multiple testing

The two-sided Mann-Kendall test is applied to each cell's annual compound frequency. The Sen slope is reported as percentage-point change per decade. The existing minimum of 10 valid years and 70% year coverage is retained, and the annual variance is adjusted using the project's approximate lag-1 AR(1) effective-sample-size method.

Benjamini-Yekutieli (BY) adjusted p-values are the primary spatial evidence classification because they are valid under general dependence among tests, albeit conservative. Benjamini-Hochberg (BH) adjusted p-values are retained as a sensitivity comparison. Raw p-values and both adjusted values remain in the output table.

### Quality control and traceability

Before analysis, the regional grid validator checks required columns, cell-month uniqueness, coordinate consistency, units, broad physical bounds, valid observation counts and cell-level coverage. Missing observations and absent cell-month records are reported separately. Duplicate keys and implausible values block analysis. A cell below the configured coverage threshold is not eligible for the primary run.

The run package retains the input file hashes, source request metadata, boundary file hash, validation report, processing parameters, per-cell diagnostics, monthly indicators, annual frequencies and trend table.

### Interpretation limits

- The indicator is retrospective. It does not yet issue forecasts or warning lead times.
- SPI-3 describes precipitation deficits, not root-zone soil moisture or evaporative demand.
- The temperature component is a monthly anomaly, not a daily extreme-temperature or human heat-stress index.
- A joint hot-dry classification is a statistical co-occurrence indicator, not an estimate of crop loss, health impact, fire risk or water-supply impact.
- NASA POWER is a gridded estimate, not a station observation. Spatial resolution is retained as returned and can vary by source product.
- The Ghana country boundary is used to select grid-cell centres. It is not the spatial measurement unit.
- The result requires comparison with independent precipitation products and, where available, station observations before operational use.

## 13. Independent precipitation validation pathway

The planned precipitation cross-check uses NASA GPM IMERG Final Run monthly precipitation over the common period beginning in 1998. IMERG has a 0.1° grid and a 30-minute base sampling interval, with monthly products also available. IMERG and POWER have different retrieval methods, grid spacing and error characteristics; they will be compared after transparent spatial and temporal aggregation to a common support. They will not be merged as if they were one homogeneous record.
