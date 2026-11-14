# Ghana-wide spatial data pipeline

EarthScope's original five-location analysis remains a point/grid-cell time-series
analysis. This module adds a separate pathway for retrieving NASA POWER regional
monthly grid data over Ghana.

## Data source

NASA POWER Monthly Regional API:

`https://power.larc.nasa.gov/api/temporal/monthly/regional`

The API accepts one parameter per regional request and requires at least a 2-degree longitude range. The downloader divides the Ghana bounding box into balanced request tiles, then combines returned cell records by their actual coordinates. It does not interpolate, resample, or assign a city trend to an entire administrative district.

NASA documents current native spatial resolutions of approximately 0.5° ×
0.625° for meteorological parameters and 1° × 1° for solar parameters. The
returned cell-centre coordinates are retained and the observed spacing is
summarised separately for each variable. Do not assume the variables share
one grid.

Meteorological monthly products begin in 1981. Solar irradiance products begin
in 1984. Each series is limited to its documented temporal availability.

## Download

From the repository root:

```bash
python -m scripts.fetch_power_regional --start 1981 --end 2025
```

Fetch selected parameters:

```bash
python -m scripts.fetch_power_regional --variables T2M,PRECTOTCORR --start 2001 --end 2025
```

Output files are written to `data/spatial/nasa_power/` by default:
- One CSV per variable, preserving native cell coordinates and monthly values.
- `fetch_metadata.json`, containing the request tiles, response status, returned
  cell counts, units when supplied by the response, and observed grid spacing.

The CSV files are not committed to the repository by default. They are generated
locally or in a deployment data volume after the live endpoint has been verified.

## Validation status and cautions

A live NASA POWER regional smoke test succeeded for all seven variables over
2020–2021. The Ghana bounding-box requests returned 91 cells per meteorological variable
at 0.5° latitude × 0.625° longitude spacing. The solar request returned 24 cells
at 1° × 1° spacing. These counts are before filtering cell centres to the national
boundary and should not be read as the number of Ghana-only cells. This confirms the live request format and parameter access
for that sample period. It does not yet validate the complete 1981–2025 archive.

Automated tests also use mocked GeoJSON fixtures. They verify tiling, parsing,
missing-value handling, coordinate preservation, per-cell summaries, trend
statistics, and map legends.

Before treating the full historical grid as validated, fetch the complete requested
period and inspect coverage, missing values, units, cell counts and duplicate
coordinates at tile boundaries. The current live smoke test confirms endpoint
access and response parsing for a two-year sample, not every year of the archive.

NASA POWER regional grid values are gridded estimates, not direct weather
station observations. They are not sufficiently detailed to represent
neighbourhood-scale conditions within Accra. For urban-scale temperature
mapping, use an appropriate higher-resolution satellite land-surface
temperature product as a separate dataset and analysis pathway.


## Spatial Explorer display

The dashboard's Spatial Explorer retrieves only the selected variable and
period, then caches the result for seven days. It offers:
- Period mean by native grid cell.
- Per-cell annual Mann–Kendall and Sen's slope results, with AR(1) effective
  sample-size correction and Benjamini–Hochberg FDR adjustment across cells.
- A map legend and cell-level tooltips.
- Ghana ADM2 boundaries to retain cell centres inside the national boundary and clip approximate cell footprints.

Cell rectangles are approximate display footprints inferred from returned
cell-centre spacing and clipped to Ghana administrative boundaries. They are
not official NASA cell polygons. The dashboard does not interpolate between
cells or treat an administrative district as the measurement unit.


## Experimental compound hot-dry analysis

A separate retrospective climate-stress pathway combines monthly T2M and
PRECTOTCORR values on their common native NASA POWER grid cells. It does not
change the existing five-location trend pipeline.

Run after downloading the two required variables:

```bash
python -m scripts.fetch_power_regional --variables T2M,PRECTOTCORR --start 1981 --end 2025
python -m scripts.validate_regional_grid --variables T2M,PRECTOTCORR --start 1981 --end 2025
python -m scripts.run_compound_analysis --start 1981 --end 2025
```

The compound engine standardises T2M by calendar month against 1991–2020,
calculates trailing three-month precipitation totals from the monthly mean
daily precipitation rate, fits a zero-adjusted gamma distribution for SPI-3
separately for each ending calendar month, and flags months with T2M z-score
at least +1 and SPI-3 at or below -1. Annual frequency is the percentage of
classifiable months that meet both conditions. At least nine classifiable
months are required for an annual value.

For each native grid cell, annual compound frequency is tested using
Mann–Kendall with the project's approximate AR(1) variance adjustment and
Sen's slope. Benjamini–Yekutieli is the primary spatial multiple-testing
correction; Benjamini–Hochberg is retained as a sensitivity result. A separate
exploratory Mann–Kendall diagnostic is calculated for the unweighted mean annual
frequency across retained grid-cell centres. That single aggregate series is
not an area-weighted national estimate and does not replace the cell-level
multiple-testing results.

The run writes:
- `compound_hot_dry_monthly.csv`: monthly temperature anomaly, SPI-3 and event classification.
- `compound_hot_dry_annual_frequency.csv`: annual percentage and valid-month count by cell.
- `compound_hot_dry_cell_trends.csv`: per-cell Sen slope, confidence interval, raw p-value, BY/BH adjusted p-values and evidence classes.
- `compound_hot_dry_annual_summary.csv`: annual event counts, number of grid cells with events and unweighted cell-frequency summaries.
- `compound_hot_dry_cell_summary.csv`: event counts, assessed years, frequency summaries and trend evidence by grid cell.
- `compound_hot_dry_cell_centres.geojson`: point features at returned grid-cell centres. These are not official grid-cell polygons or station locations.
- `analysis_run.json`: input hashes, quality-control summaries, boundary provenance, analysis parameters and output counts.
- `ghana_adm0_boundary.geojson`: the boundary geometry used for cell-centre selection.

The workflow `.github/workflows/compound-climate-stress.yml` can retrieve the
1981–2025 T2M and PRECTOTCORR regional grids, validate them, run the compound
analysis and publish the outputs as a GitHub Actions artifact.

This product is an experimental retrospective indicator. It is not a
heatwave definition, an impact model, a soil-moisture drought index, or an
operational forecast. A later validation stage should compare precipitation
behaviour against NASA GPM IMERG over their common period from 1998 onward.


## First complete Ghana compound hot-dry run (14 November 2026)

The first complete 1981–2025 regional execution is recorded in
[GitHub Actions run 43607680465](https://github.com/Mikeswr/earthscope/actions/runs/43607680465).
The associated research artifact is
[earthscope-ghana-compound-hot-dry-1981-2025](https://github.com/Mikeswr/earthscope/actions/runs/43607680465/artifacts/14119156745).

The two regional variables passed quality control. Each returned 91 grid
cells and 49,140 monthly rows with 100% valid-month coverage. After selecting
cell centres inside the geoBoundaries Ghana ADM0 geometry, 61 common cells
were retained. Outputs include 32,940 monthly rows and 2,745 annual cell-year
records.

Of 32,818 classifiable cell-months, 2,099 (6.40%) met the compound hot-dry
thresholds. The most spatially widespread years in this record were 1983
(61/61 cells), 2001 (59/61), 2013 (58/61), 1987 (56/61), 1998 (54/61),
2015 (54/61), and 2000 (52/61). 1998 had the largest total number of
classified compound cell-months (283).

No cell-level trend was significant after either Benjamini–Yekutieli or
Benjamini–Hochberg correction. Two of 61 raw cell p-values were below 0.05,
but neither survived correction. All 61 Sen slope estimates were zero because
the annual cell-frequency series are heavily tied and zero-inflated: 68.1% of
cell-years had no classified compound month.

The exploratory unweighted mean annual frequency across the 61 cells had a
Sen slope of +0.0408 percentage points per decade (95% interval -0.5855 to
+0.9320) and an AR(1)-adjusted Mann–Kendall p-value of 0.6854. It did not show
a statistically significant monotonic trend. This mean is not an area-weighted
national estimate.

These results support the description of episodic compound hot-dry
co-occurrence in this NASA POWER record. They do not support a claim of a
persistent increasing trend across Ghana. They are not an operational warning
or impact assessment.

Limitations to retain in any presentation:
- NASA POWER values are gridded estimates, not station observations.
- The 61 retained points are returned grid-cell centres, not station sites or
  official cell polygons. No spatial interpolation was used.
- The geoBoundaries ADM0 geometry used by the first run represents 2007.
- The regional API metadata captured units and coordinates but did not identify
  the underlying source product for every month. NASA POWER meteorological
  services use MERRA-2 and GEOS-IT source products; see the
  [NASA POWER source documentation](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/).
- Independent precipitation cross-product evaluation against GPM IMERG Final
  over the common 1998–2025 period remains pending. IMERG uses a finer
  0.1-degree grid and a distinct retrieval chain, but its Final Run also uses
  monthly gauge adjustment. This comparison must not be described as station
  validation. See the [NASA GPM data directory](https://gpm.nasa.gov/data/directory).

EarthScope is a NASA-data-based research prototype. It is not a NASA
programme, partnership, endorsement, or operational warning service.
