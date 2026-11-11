# EarthScope trend analysis report

Data: NASA POWER gridded estimates (reanalysis and satellite based sources), not station observations. Five locations are analysed separately. They are not a spatial sample, and nothing here is a spatial trend map.

## 1. What was done

For each of 35 series (7 variables x 5 locations) I built an annual value from the twelve monthly values and tested it for a monotonic trend with the Mann-Kendall test. The annual value is the day-weighted mean for T2M, PRECTOTCORR, RH2M, WS10M and ALLSKY_SFC_SW_DWN, the annual maximum of the monthly values for T2M_MAX and the annual minimum for T2M_MIN. A year needs all 12 valid months. A series needs at least 10 valid years covering at least 70 percent of its nominal span; the span counts flagged years at the start, middle and end. Sen's slope uses the actual elapsed years and is given per decade with a 95 percent interval. No value was interpolated or filled.

Autocorrelation: the Mann-Kendall variance is inflated using the lag-1 autocorrelation of the Sen-detrended series (an effective sample size approach, never reducing the variance). In my simulations with AR(1) noise this stayed much closer to the nominal error rate than Hamed-Rao, but it is not exact at strong autocorrelation (METHODS.md). Hamed-Rao and no correction are reported as sensitivity runs.

Multiple testing: Benjamini-Hochberg FDR at 0.05, applied within two pre-declared families. The primary family is the six meteorological variables at five locations (30 tests). ALLSKY_SFC_SW_DWN is a secondary family (5 tests) because it blends several source products over time and starts in 1984. Locations and variables are not independent (neighbouring variables such as T2M, T2M_MAX and T2M_MIN move together), so FDR here is approximate.

The seasonal Mann-Kendall test is computed and kept in the tables, but I do not use it for any significance statement. It treats calendar months as independent, and in these data it gives p values near zero where the annual test finds nothing (for example Kumasi T2M), which is what ignoring between-month correlation would produce.

Descriptive trends and statistically supported findings are kept apart. Every series has a descriptive Sen slope. Only series in the class significant after FDR are treated as findings.

## 2. Summary

Of 35 series: 10 are significant after FDR, 3 are significant only before FDR correction (not claimed as findings), 22 are not significant, 0 had insufficient data.

### 2a. Statistically supported (significant after FDR within family)

| location | variable | unit | Sen slope per decade | 95% low | 95% high | Kendall tau | z | p uncorrected | p FDR | lag-1 autocorrelation | variance factor | family | unchanged in every sensitivity run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Takoradi | T2M | C | 0.1258 | 0.0806 | 0.1891 | 0.4869 | 4.5662 | 0.0000 | 0.0000 | 0.0307 | 1.0618 | primary | yes |
| Accra | T2M | C | 0.1823 | 0.1407 | 0.2123 | 0.6242 | 6.0357 | 0.0000 | 0.0000 | -0.1536 | 1.0000 | primary | yes |
| Tamale | T2M | C | 0.2844 | 0.1064 | 0.4562 | 0.4020 | 2.9128 | 0.0036 | 0.0179 | 0.2864 | 1.7776 | primary | no |
| Wa | PRECTOTCORR | mm/day | 0.1714 | 0.0739 | 0.2891 | 0.3212 | 2.9452 | 0.0032 | 0.0179 | 0.0527 | 1.1086 | primary | no |
| Takoradi | RH2M | % | 0.9481 | 0.4813 | 1.3097 | 0.4848 | 3.6649 | 0.0002 | 0.0019 | 0.2464 | 1.6347 | primary | yes |
| Accra | RH2M | % | 0.8109 | 0.5960 | 1.0363 | 0.6081 | 5.0125 | 0.0000 | 0.0000 | 0.1618 | 1.3757 | primary | yes |
| Accra | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | -0.0514 | -0.0716 | -0.0285 | -0.4843 | -3.6103 | 0.0003 | 0.0008 | 0.2239 | 1.5594 | secondary_solar | yes |
| Kumasi | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | -0.0364 | -0.0659 | -0.0106 | -0.3659 | -2.6001 | 0.0093 | 0.0116 | 0.2692 | 1.7129 | secondary_solar | yes |
| Tamale | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | -0.0395 | -0.0610 | -0.0184 | -0.4518 | -3.1411 | 0.0017 | 0.0028 | 0.2907 | 1.7920 | secondary_solar | yes |
| Wa | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | -0.0427 | -0.0577 | -0.0221 | -0.4100 | -3.6294 | 0.0003 | 0.0008 | 0.0510 | 1.1048 | secondary_solar | yes |

8 of these 10 kept their class in every sensitivity run (section 5); the others should be read with the caution given there.

Implied change over the record (Sen slope x record length, descriptive):

| location | variable | unit | first_year | last_year | implied change |
|---|---|---|---|---|---|
| Takoradi | T2M | C | 1981 | 2025 | 0.55 |
| Accra | T2M | C | 1981 | 2025 | 0.80 |
| Tamale | T2M | C | 1981 | 2025 | 1.25 |
| Wa | PRECTOTCORR | mm/day | 1981 | 2025 | 0.75 |
| Takoradi | RH2M | % | 1981 | 2025 | 4.17 |
| Accra | RH2M | % | 1981 | 2025 | 3.57 |
| Accra | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | 1984 | 2025 | -0.21 |
| Kumasi | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | 1984 | 2025 | -0.15 |
| Tamale | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | 1984 | 2025 | -0.16 |
| Wa | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | 1984 | 2025 | -0.17 |

### 2b. Significant before FDR only (not findings)

| location | variable | unit | Sen slope per decade | 95% low | 95% high | Kendall tau | z | p uncorrected | p FDR | lag-1 autocorrelation | variance factor | family |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tamale | T2M_MAX | C | 0.3166 | 0.0211 | 0.6406 | 0.2545 | 2.1061 | 0.0352 | 0.1173 | 0.1559 | 1.3597 | primary |
| Accra | T2M_MIN | C | 0.1817 | 0.0264 | 0.3194 | 0.2465 | 2.3781 | 0.0174 | 0.0746 | -0.0275 | 1.0000 | primary |
| Tamale | PRECTOTCORR | mm/day | -0.1493 | -0.2739 | -0.0243 | -0.2707 | -2.2738 | 0.0230 | 0.0862 | 0.1409 | 1.3195 | primary |

### 2c. Not significant: descriptive slopes only

| location | variable | unit | Sen slope per decade | 95% low | 95% high | p uncorrected | p FDR |
|---|---|---|---|---|---|---|---|
| Kumasi | T2M | C | 0.0657 | -0.0696 | 0.2147 | 0.3598 | 0.4907 |
| Wa | T2M | C | 0.0281 | -0.1640 | 0.2009 | 0.7750 | 0.8303 |
| Takoradi | T2M_MAX | C | -0.2336 | -0.5051 | 0.0176 | 0.0582 | 0.1393 |
| Accra | T2M_MAX | C | 0.1053 | -0.0057 | 0.2246 | 0.0577 | 0.1393 |
| Kumasi | T2M_MAX | C | -0.3344 | -0.8659 | 0.2139 | 0.1963 | 0.3271 |
| Wa | T2M_MAX | C | 0.0500 | -0.1301 | 0.2465 | 0.6316 | 0.7288 |
| Takoradi | T2M_MIN | C | 0.0348 | -0.1450 | 0.1859 | 0.6955 | 0.7728 |
| Kumasi | T2M_MIN | C | -0.0513 | -0.4136 | 0.3341 | 0.9065 | 0.9367 |
| Tamale | T2M_MIN | C | 0.1713 | -0.1336 | 0.5000 | 0.2523 | 0.3784 |
| Wa | T2M_MIN | C | -0.0921 | -0.4685 | 0.1777 | 0.6317 | 0.7288 |
| Takoradi | PRECTOTCORR | mm/day | 0.0092 | -0.2577 | 0.3018 | 0.9367 | 0.9367 |
| Accra | PRECTOTCORR | mm/day | 0.1723 | -0.0063 | 0.3712 | 0.0604 | 0.1393 |
| Kumasi | PRECTOTCORR | mm/day | 0.1053 | -0.2816 | 0.5034 | 0.5405 | 0.6757 |
| Kumasi | RH2M | % | 0.6961 | -0.2474 | 1.6030 | 0.1205 | 0.2126 |
| Tamale | RH2M | % | -0.6459 | -2.3736 | 1.0776 | 0.3552 | 0.4907 |
| Wa | RH2M | % | 1.1739 | -0.3041 | 2.5099 | 0.1030 | 0.2013 |
| Takoradi | WS10M | m/s | -0.0249 | -0.0632 | 0.0187 | 0.2369 | 0.3740 |
| Accra | WS10M | m/s | -0.0357 | -0.0767 | 0.0075 | 0.0820 | 0.1757 |
| Kumasi | WS10M | m/s | -0.0291 | -0.0644 | 0.0017 | 0.0586 | 0.1393 |
| Tamale | WS10M | m/s | 0.0180 | -0.0359 | 0.0761 | 0.4356 | 0.5681 |
| Wa | WS10M | m/s | -0.0333 | -0.0730 | 0.0076 | 0.1073 | 0.2013 |
| Takoradi | ALLSKY_SFC_SW_DWN | kW-hr/m^2/day | -0.0063 | -0.0230 | 0.0154 | 0.4631 | 0.4631 |

A slope in this table describes these years at this grid cell. The 95 percent interval includes zero in 22 of 22 rows and no p value survives correction, so none of it is evidence of a trend.

## 3. Results by variable

**T2M** (C per decade): Takoradi +0.126, Accra +0.182, Tamale +0.284 significant after FDR; Kumasi +0.066, Wa +0.028 not supported.

**T2M_MAX** (C per decade): none significant after FDR; Takoradi -0.234, Accra +0.105, Kumasi -0.334, Tamale +0.317, Wa +0.050 not supported.

**T2M_MIN** (C per decade): none significant after FDR; Takoradi +0.035, Accra +0.182, Kumasi -0.051, Tamale +0.171, Wa -0.092 not supported.

**PRECTOTCORR** (mm/day per decade): Wa +0.171 significant after FDR; Takoradi +0.009, Accra +0.172, Kumasi +0.105, Tamale -0.149 not supported.

**RH2M** (% per decade): Takoradi +0.948, Accra +0.811 significant after FDR; Kumasi +0.696, Tamale -0.646, Wa +1.174 not supported.

**WS10M** (m/s per decade): none significant after FDR; Takoradi -0.025, Accra -0.036, Kumasi -0.029, Tamale +0.018, Wa -0.033 not supported.

**ALLSKY_SFC_SW_DWN** (kW-hr/m^2/day per decade): Accra -0.051, Kumasi -0.036, Tamale -0.039, Wa -0.043 significant after FDR; Takoradi -0.006 not supported.

Signs in the tables run opposite for some variables across locations, and significant and non-significant locations sit side by side (for example T2M is significant at Takoradi, Accra and Tamale, not at Kumasi or Wa). With five points I do not read that as a regional pattern.

## 4. Autocorrelation treatment

Estimated lag-1 autocorrelation of the detrended annual series ranges from -0.22 to 0.54 (median 0.18). The resulting variance factor ranges from 1.00 to 3.26; a factor of 1 means no inflation. P values under the three treatments for the series that are significant after FDR in the primary run:

| location | variable | p Hamed-Rao correction | p no autocorrelation correction | p ar1_neff (primary) |
|---|---|---|---|---|
| Takoradi | T2M | 0.00000 | 0.00000 | 0.00000 |
| Accra | T2M | 0.00000 | 0.00000 | 0.00000 |
| Tamale | T2M | 0.00002 | 0.00010 | 0.00358 |
| Wa | PRECTOTCORR | 0.00096 | 0.00193 | 0.00323 |
| Takoradi | RH2M | 0.00000 | 0.00000 | 0.00025 |
| Accra | RH2M | 0.00000 | 0.00000 | 0.00000 |
| Accra | ALLSKY_SFC_SW_DWN | 0.00001 | 0.00001 | 0.00031 |
| Kumasi | ALLSKY_SFC_SW_DWN | 0.00001 | 0.00067 | 0.00932 |
| Tamale | ALLSKY_SFC_SW_DWN | 0.00025 | 0.00003 | 0.00168 |
| Wa | ALLSKY_SFC_SW_DWN | 0.00014 | 0.00014 | 0.00028 |

## 5. Robustness to analysis choices

Each series was re-run with: no autocorrelation correction; Hamed-Rao; Benjamini-Yekutieli FDR; T2M_MAX and T2M_MIN as the annual mean of monthly extremes (those two variables only); the common period 1984 to 2025; and PRECTOTCORR without months more than 5 mm/day above the calendar-month mean (PRECTOTCORR only). Only the runs that apply to a variable are counted for it.

| primary_evidence_class | series | unchanged_in_all_runs |
|---|---|---|
| not_significant | 22 | 12 |
| significant_after_fdr | 10 | 8 |
| significant_before_fdr_only | 3 | 0 |

The findings that did not keep their class in every run:

| location | variable | n_sensitivity_runs | n_same_evidence_class | differing_runs |
|---|---|---|---|---|
| Tamale | T2M | 4 | 2 | Benjamini-Yekutieli FDR; common period 1984-2025 |
| Wa | PRECTOTCORR | 5 | 3 | Benjamini-Yekutieli FDR; PRECTOTCORR without months more than 5 mm/day above the calendar-month mean |

Of the 3 series significant before FDR only, 0 kept that class in every run. Slope sign was the same in every run for 10 of 10 series significant after FDR. Full tables: reports/tables/sensitivity_robustness.csv and sensitivity_all_scenarios.csv.

## 6. Data concerns that bear on the trends

Precipitation is the weakest part. Of the five precipitation series, one is significant after FDR (Wa, increasing), and it falls to significant before FDR only when the extreme months are excluded or when the more conservative FDR is used. The early extreme months at Kumasi and Takoradi, and a step remaining after detrending at Takoradi around 2016 and at Kumasi around 1988, mean the southern rainfall slopes should not be trusted until checked against independent data.

ALLSKY_SFC_SW_DWN declines at four locations. The variable blends source products and its record is shorter, so a change in the source could look like a trend. The detrended Pettitt test found no step in any of the five solar series, which is weak reassurance given its limited power. The decline is a result for this product, not yet a confirmed change in surface radiation.

T2M_MAX and T2M_MIN, now analysed as annual extremes, show no series that is significant after FDR. Tamale T2M_MAX and Accra T2M_MIN are significant before correction only.

## 7. Figures

reports/figures/trend_summary_forest.png shows all slopes with intervals, marked by evidence class. reports/figures/trend_<VARIABLE>.png shows the annual series and Sen slope for each variable, with a solid line when significant after FDR and a dashed line otherwise. t2m_monthly_anomalies.png and qc_precipitation_flagged_months.png support the data quality discussion.

Provenance of this run: analysis_run.json holds the input checksum, software versions, thresholds and scenarios.
