# Ghana IMERG–POWER comparison: interpretation note

**Analysis period:** January 1998 to September 2025  
**Grid:** 61 Ghana grid-cell centres retained from the existing 2007 ADM0 boundary workflow  
**Monthly pairs:** 20,313 of 20,313 (100% paired coverage)

This note interprets the completed run of the reproducible cross-product comparison workflow. It is a consistency assessment, not independent station validation.

## Overall comparison

| Metric | Result |
|---|---:|
| POWER mean monthly total | 106.062 mm |
| IMERG mean monthly total | 100.256 mm |
| Pooled bias (IMERG minus POWER) | -5.805 mm |
| Pooled percentage bias | -5.47% |
| MAE | 28.219 mm |
| RMSE | 43.944 mm |
| Pearson correlation | 0.867 |
| Spearman correlation | 0.913 |
| Median cell Pearson correlation | 0.863 |
| Median cell MAE | 27.251 mm |

Pooled statistics describe the combined cell-month pairs and must not be interpreted as independent-sample inference. Months are serially dependent and neighbouring cells are spatially dependent.

## Seasonal differences

The seasonal summaries below are averages or medians across the 61 cell-level seasonal metrics. Bias is IMERG minus POWER.

| Season | Mean cell bias (mm/month) | Median cell bias | Median cell Pearson r | Mean cell MAE |
|---|---:|---:|---:|---:|
| DJF | +1.23 | +1.22 | 0.652 | 9.31 |
| MAM | +1.63 | +3.64 | 0.614 | 31.10 |
| JJA | -16.86 | -18.34 | 0.669 | 42.49 |
| SON | -9.21 | -7.55 | 0.889 | 29.79 |

The clearest seasonal feature is a negative IMERG-minus-POWER difference in JJA and SON. DJF and MAM have small positive mean differences overall, although the direction varies by cell. The JJA and MAM median correlations are lower than SON, suggesting that matching monthly variability is season-dependent. The small DJF rainfall totals also mean that absolute errors are smaller, but relative errors can be large.

## Spatial pattern

Across the 61 cells:
- 40 cells have a negative mean bias and 21 have a positive mean bias.
- Cell mean bias ranges from -24.31 to +10.20 mm/month.
- The five most negative cell biases are between -21.66 and -24.31 mm/month.
- The five most positive cell biases are between +6.35 and +10.20 mm/month.
- Cell-level Pearson correlation ranges approximately from 0.71 to 0.96.

The strongest negative biases occur in several southern and central grid cells, while positive biases occur in some northern cells. This is a descriptive pattern on the retained grid, not a claim of a statistically significant geographic gradient. The cell support is approximate and should be shown as grid-centre diagnostics, not as official POWER polygons.

## Standardised monthly anomaly agreement

For each cell and each product, monthly totals were standardised by calendar month over the comparison period. The resulting anomaly correlations have:
- Mean cell correlation: 0.562
- Median cell correlation: 0.561
- Range: 0.399 to 0.693

This is notably lower than the raw monthly-total correlation. The products broadly track wet and dry seasonal cycles, but their agreement in month-to-month anomalies is more modest. These anomaly scores are full-period descriptive correlations, not an independent out-of-sample validation.

## Data coverage and quality

All 61 cells have 333 valid paired monthly records. The median number of valid IMERG pixels contributing to a cell-month is 42. IMERG quality and gauge-weighting layers were retained as diagnostics and were not used as arbitrary exclusion thresholds. No missing values were interpolated.

## Scientific interpretation and limitations

1. This is a cross-product consistency assessment, not ground-station validation.
2. IMERG Final V07 includes monthly GPCC gauge adjustment. POWER PRECTOTCORR uses observation-corrected MERRA-2 precipitation forcing, with CMAP gauge-satellite precipitation forcing over continental Africa. The products have different processing chains but both incorporate gauge-informed precipitation information.
3. IMERG was aggregated over approximate POWER grid-cell rectangles inferred from returned cell-centre spacing. These are not official NASA POWER polygons.
4. The analysis ends in September 2025 because that is the coverage used for the selected IMERG Final V07 collection export.
5. Pooled correlations and errors are descriptive. Do not attach ordinary independent-sample significance claims to the pooled cell-month pairs.

## Recommended next analysis

Before presenting this as a validation result, perform a station-based comparison where suitable independent rain-gauge observations are available. In parallel, map cell-level bias, MAE, and anomaly correlation using the actual grid-cell centres and the Ghana boundary for geographic context. Examine the JJA and SON differences by year and by cell, and test whether the pattern is robust to alternative spatial aggregation supports.
