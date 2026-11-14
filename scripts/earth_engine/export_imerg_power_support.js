// EarthScope: export GPM IMERG monthly Final V07 to the 61 Ghana POWER grid-cell supports.
// Open https://code.earthengine.google.com, paste this script, then run the two Tasks.
// Collection: NASA/GPM_L3/IMERG_MONTHLY_V07 (Final monthly product, 1998-01 through 2025-09).
// Output is an area-weighted mean across each approximate 0.5 x 0.625 degree POWER cell footprint.
// These rectangles are inferred from returned POWER cell-centre spacing, not official POWER polygons.

var COLLECTION_ID = 'NASA/GPM_L3/IMERG_MONTHLY_V07';
var START_DATE = '1998-01-01';
var END_DATE_EXCLUSIVE = '2025-10-01';
var EXPORT_FOLDER = 'EarthScope_GPM';
var EXPORT_PREFIX = 'earthscope_ghana_imerg_monthly_power_support_1998_2025_09';

var POWER_GRID = [
  {id: '5.0000_-2.5000', lat: 5, lon: -2.5},
  {id: '5.0000_-1.8750', lat: 5, lon: -1.875},
  {id: '5.5000_-2.5000', lat: 5.5, lon: -2.5},
  {id: '5.5000_-1.8750', lat: 5.5, lon: -1.875},
  {id: '5.5000_-1.2500', lat: 5.5, lon: -1.25},
  {id: '5.5000_-0.6250', lat: 5.5, lon: -0.625},
  {id: '6.0000_-2.5000', lat: 6, lon: -2.5},
  {id: '6.0000_-1.8750', lat: 6, lon: -1.875},
  {id: '6.0000_-1.2500', lat: 6, lon: -1.25},
  {id: '6.0000_-0.6250', lat: 6, lon: -0.625},
  {id: '6.0000_-0.0000', lat: 6, lon: -0.0},
  {id: '6.0000_0.6250', lat: 6, lon: 0.625},
  {id: '6.5000_-3.1250', lat: 6.5, lon: -3.125},
  {id: '6.5000_-2.5000', lat: 6.5, lon: -2.5},
  {id: '6.5000_-1.8750', lat: 6.5, lon: -1.875},
  {id: '6.5000_-1.2500', lat: 6.5, lon: -1.25},
  {id: '6.5000_-0.6250', lat: 6.5, lon: -0.625},
  {id: '6.5000_-0.0000', lat: 6.5, lon: -0.0},
  {id: '6.5000_0.6250', lat: 6.5, lon: 0.625},
  {id: '7.0000_-2.5000', lat: 7, lon: -2.5},
  {id: '7.0000_-1.8750', lat: 7, lon: -1.875},
  {id: '7.0000_-1.2500', lat: 7, lon: -1.25},
  {id: '7.0000_-0.6250', lat: 7, lon: -0.625},
  {id: '7.0000_-0.0000', lat: 7, lon: -0.0},
  {id: '7.5000_-2.5000', lat: 7.5, lon: -2.5},
  {id: '7.5000_-1.8750', lat: 7.5, lon: -1.875},
  {id: '7.5000_-1.2500', lat: 7.5, lon: -1.25},
  {id: '7.5000_-0.6250', lat: 7.5, lon: -0.625},
  {id: '7.5000_-0.0000', lat: 7.5, lon: -0.0},
  {id: '8.0000_-2.5000', lat: 8, lon: -2.5},
  {id: '8.0000_-1.8750', lat: 8, lon: -1.875},
  {id: '8.0000_-1.2500', lat: 8, lon: -1.25},
  {id: '8.0000_-0.6250', lat: 8, lon: -0.625},
  {id: '8.0000_-0.0000', lat: 8, lon: -0.0},
  {id: '8.5000_-2.5000', lat: 8.5, lon: -2.5},
  {id: '8.5000_-1.8750', lat: 8.5, lon: -1.875},
  {id: '8.5000_-1.2500', lat: 8.5, lon: -1.25},
  {id: '8.5000_-0.6250', lat: 8.5, lon: -0.625},
  {id: '8.5000_-0.0000', lat: 8.5, lon: -0.0},
  {id: '8.5000_0.6250', lat: 8.5, lon: 0.625},
  {id: '9.0000_-2.5000', lat: 9, lon: -2.5},
  {id: '9.0000_-1.8750', lat: 9, lon: -1.875},
  {id: '9.0000_-1.2500', lat: 9, lon: -1.25},
  {id: '9.0000_-0.6250', lat: 9, lon: -0.625},
  {id: '9.0000_-0.0000', lat: 9, lon: -0.0},
  {id: '9.5000_-2.5000', lat: 9.5, lon: -2.5},
  {id: '9.5000_-1.8750', lat: 9.5, lon: -1.875},
  {id: '9.5000_-1.2500', lat: 9.5, lon: -1.25},
  {id: '9.5000_-0.6250', lat: 9.5, lon: -0.625},
  {id: '9.5000_-0.0000', lat: 9.5, lon: -0.0},
  {id: '10.0000_-2.5000', lat: 10, lon: -2.5},
  {id: '10.0000_-1.8750', lat: 10, lon: -1.875},
  {id: '10.0000_-1.2500', lat: 10, lon: -1.25},
  {id: '10.0000_-0.6250', lat: 10, lon: -0.625},
  {id: '10.0000_-0.0000', lat: 10, lon: -0.0},
  {id: '10.5000_-2.5000', lat: 10.5, lon: -2.5},
  {id: '10.5000_-1.8750', lat: 10.5, lon: -1.875},
  {id: '10.5000_-1.2500', lat: 10.5, lon: -1.25},
  {id: '10.5000_-0.6250', lat: 10.5, lon: -0.625},
  {id: '10.5000_-0.0000', lat: 10.5, lon: -0.0},
  {id: '11.0000_-0.0000', lat: 11, lon: -0.0}
];

var LAT_SPACING = 0.5;
var LON_SPACING = 0.625;
var GRID_CELLS = ee.FeatureCollection(POWER_GRID.map(function(c) {
  var geometry = ee.Geometry.Rectangle([
    c.lon - LON_SPACING / 2,
    c.lat - LAT_SPACING / 2,
    c.lon + LON_SPACING / 2,
    c.lat + LAT_SPACING / 2
  ], 'EPSG:4326', false);
  return ee.Feature(geometry, {
    cell_id: c.id,
    latitude: c.lat,
    longitude: c.lon,
    power_latitude_spacing_degrees: LAT_SPACING,
    power_longitude_spacing_degrees: LON_SPACING,
    spatial_support: 'approximate_power_cell_rectangle_from_returned_centres'
  });
}));

var MONTHLY = ee.ImageCollection(COLLECTION_ID)
  .filterDate(START_DATE, END_DATE_EXCLUSIVE)
  .sort('system:time_start');

var monthCount = MONTHLY.size().getInfo();
print('IMERG monthly image count in requested interval', monthCount);
print('Expected monthly images for Jan 1998 to Sep 2025', 333);
print('Monthly collection first image', MONTHLY.first());
print('POWER cell footprints (61)', GRID_CELLS);

if (monthCount === 0) {
  throw new Error('No IMERG monthly images were found. Check Earth Engine access and collection availability.');
}

var bands = [
  'precipitation',
  'gaugeRelativeWeighting',
  'precipitationQualityIndex',
  'randomError'
];

var reducer = ee.Reducer.mean().combine({
  reducer2: ee.Reducer.count(),
  sharedInputs: true
});

var rows = ee.FeatureCollection(MONTHLY.iterate(function(image, accumulator) {
  image = ee.Image(image);
  var date = image.date();
  var monthHours = date.advance(1, 'month').difference(date, 'hour');
  var projection = image.select('precipitation').projection();

  var sampled = image.select(bands).reduceRegions({
    collection: GRID_CELLS,
    reducer: reducer,
    crs: projection,
    scale: 11132,
    tileScale: 4
  });

  sampled = sampled.map(function(feature) {
    var rate = feature.get('precipitation_mean');
    var hasRate = ee.Algorithms.IsEqual(rate, null).not();
    var rateNumber = ee.Number(ee.Algorithms.If(hasRate, rate, 0));
    var monthTotal = ee.Algorithms.If(
      hasRate,
      rateNumber.multiply(monthHours),
      null
    );
    var dailyMean = ee.Algorithms.If(
      hasRate,
      rateNumber.multiply(24),
      null
    );
    var status = ee.Algorithms.If(
      image.propertyNames().contains('status'),
      image.get('status'),
      'not_provided_by_collection'
    );

    return feature.set({
      date: date.format('YYYY-MM-dd'),
      imerg_collection_id: COLLECTION_ID,
      imerg_product_run: 'Final monthly',
      imerg_collection_status: status,
      imerg_month_hours: monthHours,
      imerg_precipitation_mm_day_mean: dailyMean,
      imerg_precipitation_mm_month_total: monthTotal,
      imerg_native_pixel_scale_m: 11132
    });
  });

  return ee.FeatureCollection(accumulator).merge(sampled);
}, ee.FeatureCollection([])));

print('Sampled cell-month row count (expected 20,313 if 333 months x 61 cells)', rows.size());
print('Sample output row', rows.first());

var selectors = [
  'date',
  'cell_id',
  'latitude',
  'longitude',
  'power_latitude_spacing_degrees',
  'power_longitude_spacing_degrees',
  'precipitation_mean',
  'precipitation_count',
  'gaugeRelativeWeighting_mean',
  'precipitationQualityIndex_mean',
  'randomError_mean',
  'imerg_precipitation_mm_day_mean',
  'imerg_precipitation_mm_month_total',
  'imerg_month_hours',
  'imerg_native_pixel_scale_m',
  'imerg_collection_id',
  'imerg_product_run',
  'imerg_collection_status'
];

Export.table.toDrive({
  collection: rows,
  description: EXPORT_PREFIX,
  folder: EXPORT_FOLDER,
  fileNamePrefix: EXPORT_PREFIX,
  fileFormat: 'CSV',
  selectors: selectors
});

var manifest = ee.FeatureCollection([
  ee.Feature(null, {
    export_created_utc: new Date().toISOString(),
    collection_id: COLLECTION_ID,
    product: 'GPM IMERG Final Run monthly V07',
    doi: '10.5067/GPM/IMERG/3B-MONTH/07',
    start_date: START_DATE,
    end_date_inclusive: '2025-09-01',
    end_date_exclusive: END_DATE_EXCLUSIVE,
    requested_cell_count: POWER_GRID.length,
    actual_month_image_count: monthCount,
    expected_month_image_count: 333,
    expected_feature_count_if_complete: 20313,
    spatial_support: 'mean of native IMERG pixels within approximate POWER grid-cell rectangles',
    precipitation_band_units: 'mm/hr',
    monthly_total_conversion: 'precipitation_mean_mm_per_hour * actual_hours_in_calendar_month',
    quality_bands_exported: 'gaugeRelativeWeighting, precipitationQualityIndex, randomError',
    important_note: 'IMERG Final includes monthly gauge adjustment. Treat comparison with POWER PRECTOTCORR as cross-product consistency assessment, not independent station validation.'
  })
]);

Export.table.toDrive({
  collection: manifest,
  description: EXPORT_PREFIX + '_manifest',
  folder: EXPORT_FOLDER,
  fileNamePrefix: EXPORT_PREFIX + '_manifest',
  fileFormat: 'CSV'
});

Map.centerObject(GRID_CELLS, 7);
Map.addLayer(GRID_CELLS.style({color: '00ffff', fillColor: '00000000', width: 1}), {}, 'EarthScope POWER support cells');
Map.addLayer(ee.Image(MONTHLY.first()).select('precipitation'),
  {min: 0, max: 0.5, palette: ['ffffff', '73c8f2', '1659a7']},
  'IMERG monthly precipitation rate, first available month');
