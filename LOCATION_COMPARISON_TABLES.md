# EarthScope location comparison tables

NASA POWER gridded estimates, not station observations. Five separate points; the tables compare them side by side and do not describe a spatial field. Locations are ordered roughly south to north.

## Location facts

| location | latitude | longitude | elevation value in file (m) |
|---|---|---|---|
| Takoradi | 4.900 | -1.760 | 48.970 |
| Accra | 5.618 | -0.171 | 27.760 |
| Kumasi | 6.695 | -1.616 | 221.770 |
| Tamale | 9.408 | -0.843 | 157.700 |
| Wa | 10.063 | -2.503 | 283.010 |

## Mean of the annual statistic, 1991 to 2020

Mean of the annual statistic over 1991 to 2020. T2M_MAX is the mean of the yearly highest hourly values and T2M_MIN the mean of the yearly lowest, so those two rows describe extremes of the grid cell.

| variable | Takoradi | Accra | Kumasi | Tamale | Wa |
|---|---|---|---|---|---|
| T2M (C, mean) | 26.113 | 26.434 | 25.799 | 27.253 | 27.276 |
| T2M_MAX (C, annual max) | 33.295 | 32.283 | 38.251 | 40.729 | 41.561 |
| T2M_MIN (C, annual min) | 20.589 | 21.730 | 15.896 | 13.034 | 13.125 |
| PRECTOTCORR (mm/day, mean) | 4.110 | 3.079 | 3.821 | 2.959 | 2.738 |
| RH2M (%, mean) | 84.124 | 84.236 | 79.444 | 65.816 | 59.954 |
| WS10M (m/s, mean) | 2.555 | 3.478 | 2.616 | 2.921 | 3.033 |
| ALLSKY_SFC_SW_DWN (kW-hr/m^2/day, mean) | 4.972 | 4.935 | 4.724 | 5.291 | 5.556 |

## Sen slope per decade with 95 percent interval

| variable | Takoradi | Accra | Kumasi | Tamale | Wa |
|---|---|---|---|---|---|
| T2M (C per decade) | +0.126 [+0.081, +0.189] | +0.182 [+0.141, +0.212] | +0.066 [-0.070, +0.215] | +0.284 [+0.106, +0.456] | +0.028 [-0.164, +0.201] |
| T2M_MAX (C per decade) | -0.234 [-0.505, +0.018] | +0.105 [-0.006, +0.225] | -0.334 [-0.866, +0.214] | +0.317 [+0.021, +0.641] | +0.050 [-0.130, +0.246] |
| T2M_MIN (C per decade) | +0.035 [-0.145, +0.186] | +0.182 [+0.026, +0.319] | -0.051 [-0.414, +0.334] | +0.171 [-0.134, +0.500] | -0.092 [-0.469, +0.178] |
| PRECTOTCORR (mm/day per decade) | +0.009 [-0.258, +0.302] | +0.172 [-0.006, +0.371] | +0.105 [-0.282, +0.503] | -0.149 [-0.274, -0.024] | +0.171 [+0.074, +0.289] |
| RH2M (% per decade) | +0.948 [+0.481, +1.310] | +0.811 [+0.596, +1.036] | +0.696 [-0.247, +1.603] | -0.646 [-2.374, +1.078] | +1.174 [-0.304, +2.510] |
| WS10M (m/s per decade) | -0.025 [-0.063, +0.019] | -0.036 [-0.077, +0.007] | -0.029 [-0.064, +0.002] | +0.018 [-0.036, +0.076] | -0.033 [-0.073, +0.008] |
| ALLSKY_SFC_SW_DWN (kW-hr/m^2/day per decade) | -0.006 [-0.023, +0.015] | -0.051 [-0.072, -0.029] | -0.036 [-0.066, -0.011] | -0.039 [-0.061, -0.018] | -0.043 [-0.058, -0.022] |

## Evidence class

| variable | Takoradi | Accra | Kumasi | Tamale | Wa |
|---|---|---|---|---|---|
| T2M | significant_after_fdr | significant_after_fdr | not_significant | significant_after_fdr | not_significant |
| T2M_MAX | not_significant | not_significant | not_significant | significant_before_fdr_only | not_significant |
| T2M_MIN | not_significant | significant_before_fdr_only | not_significant | not_significant | not_significant |
| PRECTOTCORR | not_significant | not_significant | not_significant | significant_before_fdr_only | significant_after_fdr |
| RH2M | significant_after_fdr | significant_after_fdr | not_significant | not_significant | not_significant |
| WS10M | not_significant | not_significant | not_significant | not_significant | not_significant |
| ALLSKY_SFC_SW_DWN | not_significant | significant_after_fdr | significant_after_fdr | significant_after_fdr | significant_after_fdr |

## p values, uncorrected

| variable | Takoradi | Accra | Kumasi | Tamale | Wa |
|---|---|---|---|---|---|
| T2M | 0.0000 | 0.0000 | 0.3598 | 0.0036 | 0.7750 |
| T2M_MAX | 0.0582 | 0.0577 | 0.1963 | 0.0352 | 0.6316 |
| T2M_MIN | 0.6955 | 0.0174 | 0.9065 | 0.2523 | 0.6317 |
| PRECTOTCORR | 0.9367 | 0.0604 | 0.5405 | 0.0230 | 0.0032 |
| RH2M | 0.0002 | 0.0000 | 0.1205 | 0.3552 | 0.1030 |
| WS10M | 0.2369 | 0.0820 | 0.0586 | 0.4356 | 0.1073 |
| ALLSKY_SFC_SW_DWN | 0.4631 | 0.0003 | 0.0093 | 0.0017 | 0.0003 |

## p values after FDR (within family)

| variable | Takoradi | Accra | Kumasi | Tamale | Wa |
|---|---|---|---|---|---|
| T2M | 0.0000 | 0.0000 | 0.4907 | 0.0179 | 0.8303 |
| T2M_MAX | 0.1393 | 0.1393 | 0.3271 | 0.1173 | 0.7288 |
| T2M_MIN | 0.7728 | 0.0746 | 0.9367 | 0.3784 | 0.7288 |
| PRECTOTCORR | 0.9367 | 0.1393 | 0.6757 | 0.0862 | 0.0179 |
| RH2M | 0.0019 | 0.0000 | 0.2126 | 0.4907 | 0.2013 |
| WS10M | 0.3740 | 0.1757 | 0.1393 | 0.5681 | 0.2013 |
| ALLSKY_SFC_SW_DWN | 0.4631 | 0.0008 | 0.0116 | 0.0028 | 0.0008 |

## Data availability and quality by location

| location | series | months_per_series | valid_months | missing_months | out_of_range | months_abs_z_ge_3 | months_abs_z_ge_4 |
|---|---|---|---|---|---|---|---|
| Takoradi | 7 | 540 | 3744 | 36 | 0 | 49 | 19 |
| Accra | 7 | 540 | 3744 | 36 | 0 | 55 | 19 |
| Kumasi | 7 | 540 | 3744 | 36 | 0 | 47 | 16 |
| Tamale | 7 | 540 | 3744 | 36 | 0 | 37 | 7 |
| Wa | 7 | 540 | 3744 | 36 | 0 | 28 | 10 |

The table above contains the same numbers as the CSV files in reports/tables, which are the machine readable version of every table in these reports.
