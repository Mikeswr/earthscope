# EarthScope GPM IMERG export

Place the Google Earth Engine export CSV here with this exact filename:

`earthscope_ghana_imerg_monthly_power_support_1998_2025_09.csv`

Expected design:
- GPM IMERG Final monthly V07 collection: `NASA/GPM_L3/IMERG_MONTHLY_V07`
- Requested interval: January 1998 to September 2025
- Reference grid: 61 approximate NASA POWER cell rectangles in
  `data/reference/ghana_power_grid_cells_2007_adm0.csv`
- Expected complete export size: 20,313 cell-month records
  (333 months multiplied by 61 grid cells)
- Main precipitation band: monthly mean rate in mm/hr
- Quality diagnostics: valid IMERG pixel count, gauge-relative weighting,
  precipitation quality index and random error

Generate the export using
`scripts/earth_engine/export_imerg_power_support.js`.

After the CSV is uploaded to this folder, GitHub Actions will:
1. Retrieve matching NASA POWER PRECTOTCORR values for 1998-01 through 2025-09.
2. Validate the POWER input.
3. Compare both products on the approximate POWER grid-cell support.
4. Publish cell-level, seasonal, anomaly, annual and coverage outputs as an artifact.

Do not rename the expected CSV unless the workflow path and comparison command
are updated. Do not manually edit values or fill missing observations.
