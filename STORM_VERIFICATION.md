# Storm verification: wind, gust, RH, and maximum/minimum temperature

Storm Specific Zoom explores one archived model initialization. Choose the element,
event dates, observation tolerance, and either the shared Map Explorer selection
or metadata filters. Network and elevation filters have
no station cap. Generate the analysis to load the run; changing inputs leaves the
saved result labeled with its original settings until you generate again.

## Spatial snapshot

Select an actual available valid time, labeled with hours since initialization,
or a forecast date for maximum/minimum temperature.
Deterministic elements provide forecast, observation, signed error and absolute
error maps. Probabilistic elements also provide observed-percentile, median-error,
interval-width and threshold-probability maps. Probability calculations use the
same threshold direction and shared quantile interpolation as other pages.
Each display explains the question it answers. A labeled color bar uses the same
colormap and numeric limits as the station markers; probability ticks and tooltips
show percentages. Outline colors distinguish observed events on probability maps.
Wind direction error is available when both archived forecast and matched observed
directions exist. Calm/nonpositive speeds are excluded, with an additional
observed-speed minimum for the direction map.

Circles require valid coordinates and a value for the selected display. Missing
observations do not suppress forecast-only map information. Click a station to
populate Station detail; this selection is local to the storm page. Zoom controls
and optional wheel zoom work as in Map Explorer, and selections preserve the camera.
On probability maps, green outlines indicate observed events, purple non-events,
and gray missing observations. Gold identifies the selected detail station.

## Percentiles, spread and coverage

Observation ranks interpolate between available archived quantiles. Exact ties
show the archived percentile range occupied by that value; the midpoint is used
only as a map color. Values beyond the available tails are labeled below/above the
outer archived quantile, not assigned an exact 0th/100th percentile. All-equal
quantiles are retained. Missing/insufficient and crossing quantile sets are excluded
from rank and interval diagnostics. A median-error map requires an archived p50.

p25–p75, p10–p90 and p5–p95 summaries report mean/median interval widths and observed
coverage. All displayed intervals use the same stations with matched observations
and valid bounds for every available interval. Endpoints count as covered. p5–p95
is not an ensemble min–max range. Snapshot coverage is descriptive, not evidence of
long-term calibration. Do not interpret mean widths as a pooled regional forecast
distribution or treat stations as statistically independent.

## Evolution and station detail

Evolution plots show spread/coverage for probabilistic elements, or point errors
for deterministic elements, along with sample counts. The optional fixed-station
cohort requires a matched observation (and valid interval bounds, where available)
at every loaded forecast projection. Otherwise the station population can change
with projection, and the counts make this visible.

Station plumes show archived p5–p95, p10–p90 and p25–p75 bands when available,
the selected point percentile and actual report timestamps. Invalid distributions
are not shaded. Point errors use the selected percentile; median-error maps use
p50. RH axes use 0–100%. Case tables retain the actual matched observation time and
offset, with missing observations left missing and recorded zeros retained.

Single-run forecasts are deduplicated by station/verification target, keeping the last row.
NDFD references are reconstructed by the existing loader. Nearest-report matching
uses the selected tolerance (URMA analysis matching remains exact). Daily extremes
use the same configured date matching as Model Comparison, without a reporting-time
tolerance. Accumulation views remain future work, and snow requires its appropriate
verification dataset.

## Maximum and minimum temperature

Daily snapshots, coverage summaries, and evolution charts use the configured
forecast date rather than treating an archive valid timestamp as an instantaneous
temperature. This matters because QMD maximum-temperature samples use 12Z timestamps
and NDFD samples use 00Z. These timestamps are not used to infer forecast measurement
windows. Archived initialization times and lead hours remain available in case tables.

Observation windows and their end-time offsets from archive valid times are retained
in case tables and exports. The end-time offset is diagnostic, not a matching
tolerance. Date duplicates follow the existing shared matching convention, keeping
the last eligible archived row. Missing window metadata stays unknown and does not
change the shared date match.

The station temperature plot compares the selected forecast percentile (or deterministic
forecast) and matched observed extreme on each forecast date. Available quantile
intervals are vertical bands; temperatures are not connected as an instantaneous
time series. A separate strip shows the actual observation measurement windows in
UTC, including windows ending the next day or month. No forecast interval is invented.
Negative and zero temperatures remain valid. Minimum-temperature events default to
<=32°F, with threshold and direction configurable. Temperature values, widths, and
errors are displayed in °F.
