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

Before enabling a public map, run the downloader for a short period (for example
2020–2021) and inspect:
1. HTTP success and response structure for every parameter.
2. Actual feature count and coordinates per tile.
3. Duplicate coordinates at tile boundaries.
4. Unit metadata and fill values.
5. Native grid spacing against NASA's current product documentation.

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
- Optional Ghana ADM2 boundaries for geographic context.

Cell rectangles are approximate display footprints inferred from returned
cell-centre spacing. They are not official NASA cell polygons. The dashboard
does not interpolate between cells or treat an administrative district as
the measurement unit.
