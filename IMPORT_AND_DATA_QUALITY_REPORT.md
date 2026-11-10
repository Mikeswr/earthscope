# EarthScope import and data quality report

These are NASA POWER monthly point files for five Ghanaian locations. NASA POWER values are gridded estimates built from reanalysis and satellite based sources. They are not direct station observations, and everything below should be read that way.

## 1. Files imported

| location | file | bytes | latitude | longitude | elevation value in file (m) | km from configured point | sha256 |
|---|---|---|---|---|---|---|---|
| Takoradi | POWER_Point_Monthly_19810101_20251231_004d90N_001d76W_LST_Takoradi.json | 61330 | 4.900 | -1.760 | 48.970 | 0.000 | cb4d3ccb3702e113bd37e52a84887321c9a285b16831c7009e08aecfc4098127 |
| Accra | POWER_Point_Monthly_19810101_20251231_005d62N_000d17W_LST_Accra.json | 61284 | 5.618 | -0.171 | 27.760 | 0.000 | f1d4ece6f5b8e6b82d259c763fc209ce08fe08648ac277d7dfd8ba24e3bea4e0 |
| Kumasi | POWER_Point_Monthly_19810101_20251231_006d70N_001d62W_LST_Kumasi.json | 61346 | 6.695 | -1.616 | 221.770 | 0.000 | d3586c9444caa563274966769b481ef3a5dcd41f0fd0222647d719a259b70cbf |
| Tamale | POWER_Point_Monthly_19810101_20251231_009d41N_000d84W_LST_Tamale.json | 61238 | 9.408 | -0.843 | 157.700 | 0.000 | e8f43dfa758a3bd64e5079d1b4473cda32bcc56768aa76d0af2b30fe467e4788 |
| Wa | POWER_Point_Monthly_19810101_20251231_010d06N_002d50W_LST_Wa.json | 61170 | 10.063 | -2.503 | 283.010 | 0.000 | c847293d3d868cc3d1e7a954832199b0e2ab705df66440e14a5176128540f28d |

The SHA-256 checksum of each imported copy equals the checksum of the file as uploaded. The import record, the verbatim response header and the per-parameter metadata are stored in data/processed/power_monthly_metadata.json. Imported copies are in data/raw under canonical names, each with a small .import.json record holding the original file name.

## 2. Pre-import validation (nothing was imported until these passed)

| location | status | pass | info | warn | fail |
|---|---|---|---|---|---|
| Takoradi | warn | 50 | 0 | 1 | 0 |
| Accra | warn | 50 | 0 | 1 | 0 |
| Kumasi | warn | 50 | 0 | 1 | 0 |
| Tamale | warn | 50 | 0 | 1 | 0 |
| Wa | warn | 50 | 0 | 1 | 0 |

Every file passed with no failures. The only warning in each file is: coverage_ALLSKY_SFC_SW_DWN (540 monthly keys, 36 fill values, 0 absent keys).

What was checked in each file: that the file is valid JSON with no duplicated keys; that it is a POWER point Feature with the expected header fields; that every requested parameter was returned and has a units entry; that each unit equals the expected unit; that all parameters share one key set; that keys are YYYYMM with months 1 to 13; that the returned keys cover the header's requested range; that every year has an annual key; that file name coordinates match the coordinates inside the file; that the named location is the nearest configured location; that values are inside physical limits; and that the annual value of each parameter agrees with how its definition says it is built (section 4).

I had requested six meteorological variables (T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, RH2M, WS10M). The files also contain ALLSKY_SFC_SW_DWN, which I had not requested. I added it to the configured list after seeing it, and it is analysed as a separate, secondary family.

## 3. Parameter metadata and units (as returned by NASA)

| variable | long name in response | units in response | expected | check |
|---|---|---|---|---|
| T2M | Temperature at 2 Meters | C | C | pass |
| T2M_MAX | Temperature at 2 Meters Maximum | C | C | pass |
| T2M_MIN | Temperature at 2 Meters Minimum | C | C | pass |
| PRECTOTCORR | Precipitation Corrected | mm/day | mm/day | pass |
| RH2M | Relative Humidity at 2 Meters | % | % | pass |
| WS10M | Wind Speed at 10 Meters | m/s | m/s | pass |
| ALLSKY_SFC_SW_DWN | All Sky Surface Shortwave Downward Irradiance | kW-hr/m^2/day | kW-hr/m^2/day | pass |

The parameter metadata block is identical in all five files: yes. No unit was converted or assumed; every row carries unit_source = response_metadata (assumed units used: no).

The response states the units and long names only. It does not state which source product (MERRA-2, SRB or SYN1DEG) supplied each variable, and it does not state a spatial resolution per variable. The header title says "Source Native Resolution", which means each variable is at the native grid of its source. I have not assigned a resolution to any variable.

## 4. Statistical interpretation of each variable

| variable | definition used | annual value consistent in all five files | largest difference, annual vs aggregate of months | years compared per file |
|---|---|---|---|---|
| T2M | monthly mean of daily mean | yes | 0.0050 | 45 |
| T2M_MAX | monthly maximum of hourly values | yes | 0.0000 | 45 |
| T2M_MIN | monthly minimum of hourly values | yes | 0.0000 | 45 |
| PRECTOTCORR | monthly mean of daily precipitation rate not a monthly total | yes | 0.0050 | 45 |
| RH2M | monthly mean of daily mean | yes | 0.0049 | 45 |
| WS10M | monthly mean of daily mean | yes | 0.0050 | 45 |
| ALLSKY_SFC_SW_DWN | monthly mean of daily total | yes | 0.0002 | 42 |

The definitions come from the NASA POWER data processing page, which describes a hierarchy in which monthly values are the mean of the days and annual values the mean of the months, with maximum and minimum parameters as the stated exception: they keep the value of the original instantaneous hourly time through the hierarchy. The average of the daily maximum is a different parameter (T2M_MAX_AVG) that is not in these files.

What the data show. For T2M, PRECTOTCORR, RH2M, WS10M, ALLSKY_SFC_SW_DWN, NASA's annual value equals the day-weighted mean of the twelve monthly values to within rounding. For T2M, PRECTOTCORR, RH2M, WS10M this is a real discrimination: the annual value differs from the simple mean of the months by more than rounding. For ALLSKY_SFC_SW_DWN the day-weighted and simple means differ by less than the rounding in at least one file, so this check cannot tell them apart. For T2M_MAX the annual value equals the largest of the twelve monthly values, and for T2M_MIN the smallest, in every year at every location (all files consistent: yes). T2M_MAX is at least T2M and T2M is at least T2M_MIN in 2,700 of 2,700 location months. PRECTOTCORR monthly values are daily rates in mm/day, not monthly totals (values run from 0.00 to 18.57).

A correction to my own earlier work: I had documented T2M_MAX and T2M_MIN as the monthly mean of daily maxima and minima. That was wrong. They are the highest and lowest hourly values in the month. This changes the analysis, because the natural annual quantity for an extreme is the annual extreme. The primary analysis therefore uses the annual maximum of the twelve monthly T2M_MAX values and the annual minimum of the twelve monthly T2M_MIN values. The mean of the monthly extremes is run as a sensitivity analysis.

What is not proven. The checks above are consistent with the documented definitions, but monthly data alone cannot prove how the monthly value was computed from hourly values. Daily or hourly POWER data would be needed for that.

## 5. Actual temporal coverage

I did not assume the requested coverage was returned. The header of every file requests 19810101 to 20251231. The coverage actually returned is:

| variable | first_month | last_month | months_present | valid_months_min | valid_months_max | absent_inside_span |
|---|---|---|---|---|---|---|
| T2M | 1981-01 | 2025-12 | 540 | 540 | 540 | 0 |
| T2M_MAX | 1981-01 | 2025-12 | 540 | 540 | 540 | 0 |
| T2M_MIN | 1981-01 | 2025-12 | 540 | 540 | 540 | 0 |
| PRECTOTCORR | 1981-01 | 2025-12 | 540 | 540 | 540 | 0 |
| RH2M | 1981-01 | 2025-12 | 540 | 540 | 540 | 0 |
| WS10M | 1981-01 | 2025-12 | 540 | 540 | 540 | 0 |
| ALLSKY_SFC_SW_DWN | 1981-01 | 2025-12 | 540 | 504 | 504 | 0 |

All 35 series span 1981-01 to 2025-12 with 540 monthly values present each and 0 months absent. Missing values (the fill value -999) occur only in ALLSKY_SFC_SW_DWN: Accra, Kumasi, Takoradi, Tamale, Wa all miss 1981-01..1983-12 (36 months each), so its record starts in 1984-01. The other 30 series are complete. Nothing was interpolated or filled.

## 6. Coordinates and location identity

| location | latitude in file | longitude in file | latitude in file name | longitude in file name | nearest configured location | name agrees |
|---|---|---|---|---|---|---|
| Takoradi | 4.900 | -1.760 | 4.900 | -1.760 | Takoradi | yes |
| Accra | 5.618 | -0.171 | 5.620 | -0.170 | Accra | yes |
| Kumasi | 6.695 | -1.616 | 6.700 | -1.620 | Kumasi | yes |
| Tamale | 9.408 | -0.843 | 9.410 | -0.840 | Tamale | yes |
| Wa | 10.063 | -2.503 | 10.060 | -2.500 | Wa | yes |

File name coordinates match file coordinates within rounding for all five files, and each named location is the nearest configured location. The five points are distinct (nearest pair 193.2 km apart) and no two files share a series (pairs with mostly identical values: 0). I changed locations.yaml to the coordinates found in these files so that future downloads reproduce the same points. The elevation numbers in the files are not described in the response; I report them but do not interpret them.

## 7. Inconsistencies between the five files

Headers are identical except for the order of the `sources` list (identical as sets: yes; identical in order: no). That is cosmetic and not a data inconsistency. API version (v2.10.0), time standard (LST) and title are the same in all files. Parameter sets, parameter metadata and monthly key sets are identical. The time standard is local solar time, so day boundaries follow local solar time rather than UTC; for Ghana the difference is small, but it is recorded.

## 8. Import result

The processed table has 18,900 rows (5 locations x 7 variables x 540 months), source NASA POWER, data kind gridded_estimate_not_station_observation. Duplicate location, variable, date rows: 0. Duplicates removed when merging: 0. QC flags: {'ok': 18720, 'missing': 180}.

Round trip check: I re-read the stored raw files and compared all 18,900 monthly values with the processed table. Mismatches: 0. Fill values (180) stored as missing: 180.

## 9. Quality control results

### Missingness, duplicates and range checks

| location | duplicate_keys_in_raw_json | duplicates_removed_when_merging | duplicate_location_variable_date_rows_in_processed |
|---|---|---|---|
| Takoradi | pass | 0 | 0 |
| Accra | pass | 0 | 0 |
| Kumasi | pass | 0 | 0 |
| Tamale | pass | 0 | 0 |
| Wa | pass | 0 | 0 |

Out-of-range values (physical limits in earthscope/qc/checks.py): 0. Months absent inside a series: 0.

The full per-location, per-variable coverage table is reports/tables/qc_coverage_missingness.csv, and descriptive statistics are in qc_descriptive_statistics.csv.

### Suspicious values

I flag, and do not change, months whose anomaly against the 1991 to 2020 calendar-month mean of the same record has |z| of 3 or more. For about 540 normally distributed values roughly 1.5 would be expected per series, so counts well above that point to skewed variables, mainly precipitation, or to events worth checking.

| variable | series | months_abs_z_ge_3 | months_abs_z_ge_4 | expected_per_series_if_normal | stuck_value_runs |
|---|---|---|---|---|---|
| T2M | 5 | 37 | 4 | 1.46 | 0 |
| T2M_MAX | 5 | 25 | 3 | 1.46 | 0 |
| T2M_MIN | 5 | 36 | 9 | 1.46 | 0 |
| PRECTOTCORR | 5 | 68 | 37 | 1.46 | 0 |
| RH2M | 5 | 26 | 14 | 1.46 | 0 |
| WS10M | 5 | 10 | 1 | 1.46 | 0 |
| ALLSKY_SFC_SW_DWN | 5 | 14 | 3 | 1.36 | 0 |

Months flagged at three or more locations at once:

| variable | date | n_locations | locations | largest_anomaly | largest_abs_z |
|---|---|---|---|---|---|
| PRECTOTCORR | 1986-12 | 3 | Accra, Kumasi, Takoradi | 12.33 | 34.15 |
| PRECTOTCORR | 2025-12 | 4 | Accra, Kumasi, Takoradi, Wa | 2.94 | 11.90 |
| PRECTOTCORR | 1987-09 | 3 | Accra, Kumasi, Takoradi | 13.33 | 8.03 |
| RH2M | 1987-05 | 3 | Accra, Kumasi, Takoradi | -11.53 | 7.22 |
| PRECTOTCORR | 1990-12 | 4 | Accra, Kumasi, Tamale, Wa | 2.33 | 6.27 |
| T2M | 1982-08 | 4 | Accra, Kumasi, Takoradi, Tamale | -1.88 | 5.77 |
| RH2M | 1987-06 | 3 | Accra, Kumasi, Takoradi | -7.85 | 5.54 |
| PRECTOTCORR | 2023-11 | 3 | Accra, Kumasi, Takoradi | 3.93 | 5.51 |
| T2M_MAX | 1981-01 | 3 | Kumasi, Tamale, Wa | -5.35 | 5.09 |
| RH2M | 1983-03 | 3 | Accra, Kumasi, Takoradi | -19.73 | 5.01 |
| PRECTOTCORR | 1982-02 | 3 | Accra, Kumasi, Tamale | 3.05 | 3.91 |
Precipitation is the main concern. 27 location months have PRECTOTCORR more than 5 mm/day above the calendar-month mean (counted over all months, by period):

| location | 1981 to 1988 | 1989 to 2017 | 2018 to 2025 | all |
|---|---|---|---|---|
| Takoradi | 6 | 0 | 2 | 8 |
| Accra | 1 | 0 | 2 | 3 |
| Kumasi | 7 | 2 | 5 | 14 |
| Tamale | 0 | 0 | 0 | 0 |
| Wa | 0 | 0 | 2 | 2 |

They are concentrated in the early record at Kumasi and Takoradi and again after 2018, and Tamale has none. The largest is December 1986, when Kumasi shows 12.94 mm/day (about 400 mm in the month) and Takoradi 10.76 mm/day while Tamale and Wa show 0.00. September 1987 is also extreme at all three southern sites. I cannot tell from this file whether these are real storms or artefacts of the source data, so they are kept in the primary analysis, flagged, and tested in a sensitivity run. They need checking against independent rainfall data (see the limitations report). Large z values for Tamale and Wa in the dry season (for example 0.8 mm/day in December) come from very small climatological spreads and are small in absolute terms. See reports/figures/qc_precipitation_flagged_months.png.

RH2M also has months flagged at three southern sites together (1987-05, anomaly -11.5 percentage points; 1987-06, anomaly -7.8 percentage points; 1983-03, anomaly -19.7 percentage points). A shared signal across sites could be a real regional event or a feature of the product; I changed nothing and treat these months the same way as the rainfall months.

### Homogeneity

I ran the Pettitt change point test on each annual series. The raw test also fires on a steady trend, so I repeated it after removing the Sen trend. A hit after detrending means a step or non-linear change remains. The test assumes independent years and has limited power, so a hit is a flag to investigate and a non-hit is not proof of homogeneity.

| variable | series | raw_detected | detected_after_detrending |
|---|---|---|---|
| T2M | 5 | 3 | 0 |
| T2M_MAX | 5 | 0 | 0 |
| T2M_MIN | 5 | 0 | 0 |
| PRECTOTCORR | 5 | 5 | 2 |
| RH2M | 5 | 4 | 0 |
| WS10M | 5 | 4 | 0 |
| ALLSKY_SFC_SW_DWN | 5 | 4 | 0 |

Series with a step remaining after detrending: Kumasi PRECTOTCORR, around 1988, step -1.26, p 0.038; Takoradi PRECTOTCORR, around 2016, step +0.95, p 0.041. Full results: qc_homogeneity_pettitt.csv.
