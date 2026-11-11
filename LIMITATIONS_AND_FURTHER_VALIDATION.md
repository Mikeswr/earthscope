# EarthScope limitations and items needing further validation

## 1. What these data are

NASA POWER monthly values are gridded estimates from reanalysis and satellite based sources. They represent a grid cell, not a point, and not a weather station. Elevations and local conditions of a city differ from the cell average. Agreement with station records has not been tested here.

## 2. Scope of inference

Five locations are five separate series. They do not support a spatial trend map or a statement about Ghana as a whole, and the locations are not independent samples. Findings apply to these grid cells over 1981 to 2025 (ALLSKY_SFC_SW_DWN 1984 to 2025).

## 3. Items that need validation against independent data

- Precipitation: compare PRECTOTCORR with station rainfall or an independent gridded product, especially December 1986 and September 1987 at Kumasi, Takoradi and Accra, the other flagged months, and the change points the raw Pettitt test finds around 2015 and 2016 at Accra, Kumasi and Takoradi (after removing the linear trend a step remains only at Takoradi around 2016, and at Kumasi around 1988).
- Solar radiation: confirm the decline in ALLSKY_SFC_SW_DWN with an independent radiation product and check whether the source blend changes during the record. The response does not say which product supplies this variable in which years.
- Temperature and humidity: compare the significant T2M and RH2M trends with station data. A reanalysis trend can reflect changes in assimilated observations.
- Definitions: confirm the monthly meaning of T2M_MAX and T2M_MIN (highest and lowest hourly value) against daily or hourly POWER data. The evidence here is consistent with it but is not proof.
- Spatial resolution: the files do not state a resolution per variable. Find the native grid of each source product and record it before quoting any resolution.

## 4. Statistical limits

- The autocorrelation correction is an effective sample size adjustment. In simulation with AR(1) noise and 40 years it reduced but did not remove the excess of false positives at strong autocorrelation (about 7 to 10 percent against a nominal 5 percent at lag-1 correlation 0.6). Treat borderline p values as approximate.
- The seasonal Mann-Kendall test treats months as independent and is not used for significance. A covariance corrected seasonal test is not implemented.
- FDR is applied within two families and assumes independence or positive dependence among tests. Variables at one location, and neighbouring locations, are correlated.
- The minimum data thresholds (10 valid years, 70 percent coverage, 12 months per year) are my choices and not published standards.
- Pettitt homogeneity tests assume independent years and have limited power. A non-detection is not proof of homogeneity.
- Sen's slope intervals use the inflated variance, so they inherit the same approximation.
- Significance after FDR does not make a trend physical. Sensitivity runs show that 2 of the 10 series significant after FDR change class under at least one reasonable alternative choice.

## 5. Data handling limits

- Nothing was interpolated, filled or removed. Missing ALLSKY_SFC_SW_DWN months (1981 to 1983) stay missing and are outside every ALLSKY analysis.
- A year needs all 12 valid months to enter the annual series. This is strict and costs no years in this data set except for the solar variable.
- The files use local solar time for day boundaries. Monthly aggregation and its effect on extremes were not tested.
- Month 13 (the annual value NASA supplies) is not used. The annual series is built from the monthly values.

## 6. Software status

The validation, import, QC and trend code is covered by automated tests with synthetic fixtures and by cross checks against scipy and pymannkendall. OpenWeather current conditions and a recent four-hour history view have been tested in the deployed dashboard. Agromonitoring current weather and recent hourly history have also been tested. These live weather responses are separate from the NASA POWER analysis and are not used in the trend results. Older Agromonitoring archive access was not available for the requested January 2020 period under the tested account.
