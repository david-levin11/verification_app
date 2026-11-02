# Storm verification: wind, gust, RH, and maximum/minimum temperature

## Comparing two models within a storm

Enable **Compare another model** to compare the primary run (A) with one B run.
Choose B from models supporting the selected element, its fixed verification
percentile when probabilistic (default p50), an initialization offset, and a
reference-time tolerance. B's requested initialization is A's plus the offset;
negative offsets select older guidance. The nearest available B initialization
within tolerance is chosen once for the entire storm, with earlier runs winning
equal-distance ties. Missing projections never borrow a different B run.
The selected initialization and requested offset are displayed explicitly.

Matching reuses Model Comparison's station/target/reference and observation
rules. Scores use only cases with both forecasts and the identical matched
observation. Point fields match shared valid times, daily extrema use the shared
forecast-date convention, and precipitation requires the correct accumulation
duration plus endpoint tolerance. No temporal interpolation is performed. The
selected percentiles remain fixed across the event; intervals still show the full
available distribution. All archived lead hours are eligible.

The spatial tab adds **Model absolute-error difference**: absolute error of A
minus absolute error of B. Negative values favor A, positive favor B, and zero
is a tie. Its color bar is symmetric around zero and only shared matched stations
are plotted. Other map options and single-model uncertainty diagnostics keep
their original coverage and are labeled separately.

Evolution adds shared-case bias/MAE curves for both models and shared station
counts. Targets without shared cases remain empty, breaking the score curves.
The fixed-station option requires shared matches at every A target for this
comparison. Existing primary-model evolution/uncertainty plots remain available.

Station detail overlays A (blue), B (orange), and the shared observation (red).
Probabilistic time series have p25–p75 and p5–p95 shaded bands, percentile boundary lines, p50 median lines,
and a marker for the percentile used in scoring. Deterministic guidance has
distinct point symbols. Both probabilistic and both deterministic comparisons
are supported. Temperature observation windows and precipitation forecast/obs
windows remain visible. Full shared cases, references, leads, observation timing,
and point errors can be downloaded as CSV. If no B run or shared cases exist,
diagnostics explain the empty comparison and the primary results remain usable.

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

Station detail uses the same shaded plume style for REFS, NBMQMD and other
probabilistic time series. Darker shading spans p25–p75; lighter shading spans
p5–p95, with percentile boundary lines and a p50 median line. Lines connect
archived forecast values for display only; they do not add verification cases.
Missing/invalid quantile rows break the shading. A single available projection
uses vertical percentile ranges rather than inventing a time interval.
Daily temperature extrema retain discrete boxes and observation windows because
they represent separate forecast dates.

Wind/gust plumes show every finite observation in the requested date range at its
actual UTC report time. Small red points provide event context and larger markers
identify matched observations used for verification. Other stations and reports
outside the selected dates are excluded from the full-report overlay; zeros remain
valid. Comparison curves and forecasts still use shared matched periods.
Point-error scores use the selected percentile; the central forecast line is p50.
RH axes use 0–100%. Temperature and precipitation retain measurement-window strips.

Single-run forecasts are deduplicated by station/verification target, keeping the last row.
NDFD references are reconstructed by the existing loader. Nearest-report matching
uses the selected tolerance (URMA analysis matching remains exact). Daily extremes
use the same configured date matching as Model Comparison, without a reporting-time
tolerance. Precipitation views use the shared duration/endpoint matcher. Snow
requires its appropriate verification dataset.

## Maximum and minimum temperature

Daily snapshots, coverage summaries, and evolution charts use the configured
forecast date rather than treating an archive valid timestamp as an instantaneous
temperature. The supplied legacy QMD maximum-temperature samples use 12Z timestamps
and NDFD samples use 00Z. These timestamps are not used to infer forecast measurement
windows. Archived initialization times and lead hours remain available in case tables.

Observation windows and their end-time offsets from archive valid times are retained
in case tables and exports. The end-time offset is diagnostic, not a matching
tolerance. Date duplicates follow the existing shared matching convention, keeping
the last eligible archived row. Missing window metadata stays unknown and does not
change the shared date match.

The station temperature plot compares the forecast distribution (or deterministic
forecast) and matched observed extreme on each forecast date. Probabilistic forecasts use the quantile boxes described above; temperatures are not connected as an instantaneous
time series. A separate strip shows the actual observation measurement windows in
UTC, including windows ending the next day or month. No forecast interval is invented.
Negative and zero temperatures remain valid. Minimum-temperature events default to
<=32°F, with threshold and direction configurable. Temperature values, widths, and
errors are displayed in °F.

### Legacy temperature timestamps

The old QMD decoder recorded initialization and valid times 18 hours early for
daily extrema. The app does not automatically repair these timestamps. For the
supplied legacy MaxT convention, the stored valid date coincides with the observation
date (the day the 12Z–next-day 06Z window starts), so date pairing can still select
the intended observation. Initialization selection, run labels, and cross-model
reference offsets nevertheless use the incorrect archived reference time.

The shared forecast-target rule now maps a corrected NBM-family MaxT endpoint
at next-day 06Z back to the preceding observation date. Legacy 12Z MaxT labels,
MinT labels, and NDFD calendar-date labels retain their existing date convention.
Both loaders filter on this same target date, including the last requested day
and month boundaries. No run initialization is inferred or repaired by the app;
use the archive repair script for confirmed legacy data.

### Scrolling

Storm results use the main page scrollbar and content-sized tabs, including on
short laptop viewports. Maps retain their fixed iframe height; wheel zoom remains
opt-in. The optional browser regression checks wheel scrolling over the map and
both plots and verifies that the bottom of each display is reachable.

### UTC query boundaries

Both archive loaders explicitly set their DuckDB session time zone to UTC.
Timezone-aware observation dates are stored at UTC midnight while UI query bounds
are naive UTC timestamps. Without an explicit session zone, older DuckDB versions
can interpret the bound as local midnight: in Alaska in February that is 09Z,
which excludes the first day's 00Z observation-date row. This can leave the first
MinT projection unmatched even when its 00Z–18Z observation is present. The fix
changes query interpretation only; it does not shift or modify archived records.


## Deterministic NBM and precipitation

NBM wind, MaxT, MinT, precip6hr and precip24hr use scalar forecast values. These
combinations have no percentile selector, observed-percentile/spread maps, or
probability scores. NBMQMD distributions remain probabilistic; model comparison
can score a deterministic NBM forecast against an NBMQMD point percentile while
reporting probability scores for the probabilistic side only. NBM RH/snow and
experimental-model capabilities retain their existing configuration.

The app accepts the deterministic archiver's maxt, mint, precip6hr and precip24hr
columns (temperatures already in Fahrenheit and precipitation already in inches),
plus the existing wind_speed_kt/si10 wind columns. These intervals are decoded with
authoritative reference/endpoint timestamps by the archiver; the local legacy
percentile repair script is not part of loading these new scalar forecasts.

Storm Specific supports 6-hour and 24-hour precipitation across its map, evolution,
and station-detail views. Snapshots select an accumulation endpoint and use common
observation window-duration and endpoint-tolerance rules. The station plot shows
individual forecast/observed totals as horizontal segments over their respective
windows, with endpoint markers for deterministic forecasts. Probabilistic forecasts use
quantile bands across archived endpoints and a separate window strip. A zero is a valid dry-period total; missing reports
remain missing. The plot is not a running cumulative total. Sliding/overlapping
24-hour windows remain separate, dependent cases. Probabilistic precipitation, when
selected from NBMQMD, retains uncertainty maps and endpoint quantile intervals.



## Initialization date and UTC hour

Select **Model Init Date** from the calendar and **Model Init Hour (UTC)** from
the model-dependent dropdown. NBM/NBM_EXP core products use 01/07/13/19Z;
NBMQMD, NBMQMD_EXP, HRRR, RRFS and REFS offer 00/06/12/18Z. Deterministic NBM
MaxT/MinT/precipitation use their QMD source hours. URMA offers three-hour cycles;
NDFD offers all UTC hours because its archive reference hours are not restricted
to the other models' cycle schedules. These are selection controls, not a new
forecast-hour filter or a guarantee that every offered run is in the archive.
Changing the model/element resets an incompatible hour while keeping the date.
Existing saved dates/hours survive page navigation.
