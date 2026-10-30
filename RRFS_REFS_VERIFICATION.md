# RRFS and derived REFS verification

RRFS control and REFS support wind, gust, RH and six-hour precipitation in Map
Explorer, Aggregate Verification, Storm Zoom (including two-model overlays), and
Model Comparison. Snow and instantaneous temperature are not enabled by this change.

## Archive locations

The existing Local Archive Root contains `rrfs/{element}/YYYY_MM_archive.parquet`
and the normal observation directories. RRFS gusts use the combined wind archive
when no dedicated gust archive exists. Direction verification uses RRFS archived
directions; REFS speed percentiles do not imply a forecast wind direction.

When REFS is selected (including as comparison model B), **REFS Derived Archive
Root** points at the directory containing its element directories. It defaults to
`derived/refs` beside the model root. For example, model root `/data/model` implies
`/data/derived/refs`, but any configured derived root can be selected independently
on each page. Source/derived archives are read-only; no copying or reformatting is
required.

REFS wind and gust share `wind/YYYY_MM_archive.parquet`. Rows are filtered by
`value_column` (`wind_speed_kt`, `wind_gust_kt`, `rh`, or `precip_6h`) before
deduplication or verification. `ensemble_init_time` and `ensemble_forecast_hour`
become the app's initialization and lead; p5/p10/p25/p50/p75/p90/p95 are aliased
to the existing element-specific percentile names. Original timestamps, counts,
mean, population standard deviation (`spread`), recipes and probabilities remain
available in paired data/exports. Standard deviation is not an interval width.

All archived projections are eligible, subject to the user's day/lead selection.
Forecasts from an earlier initialization month are included when verifying targets
in the following month. Three-hour steps are not invented for six-hour guidance.

## Lead-dependent completeness

REFS is usable when `complete` is true, `n_expected > 0` and
`n_available == n_expected` on that row. No fixed 14-member requirement or
hard-coded departure schedule is used. In particular, a +60 h forecast with 6/6
members verifies normally; 5/6 does not. Even if an archive was generated with
available-member statistics, this initial integration excludes incomplete rows.
Missing values are never zeros. Load diagnostics count excluded rows; paired data,
Storm Zoom map tooltips and comparison data tables retain available/expected counts.
Different archived statistics recipes within a selection are reported.

## Probabilities and event definitions

The shared probability functions prefer archived member fractions for matching
configured events. For example, `prob_gt_34` verifies strictly `>34`, and
`prob_lt_30` verifies strictly `<30`; their 0–1 values are not percentages.
Exactly matching threshold AND operator are required. An archive's row-specific
`statistics_config` decides whether that variable configured the event; a column
populated only for a different variable is not evidence of configuration.

Missing or invalid probabilities for a configured event remain unavailable, even
if percentiles exist. For an unarchived threshold/operator (including `>=`/`<=`
when only strict probabilities exist), the app uses its labeled quantile
approximation with existing ties/tails rules. It does not interpolate probability
columns across thresholds. Storm case tables expose the probability source.
Brier score, reliability diagrams and probability maps all use these same rules.
NBMQMD's existing probability approximations remain available.

Select the event definition explicitly: REFS archives usually use `>` for wind,
gust and precipitation and `<` for low RH; the UI can retain a previously selected
operator. Point scores use the fixed selected percentile. REFS p25–p75 boxes and
p5–p95 whiskers still show the distribution, and deterministic RRFS uses points.

## Six-hour precipitation

RRFS and HRRR use `precip_6h` when archived. Missing values in an existing interval
column remain missing. Older cumulative-only files derive the six-hour amount
from exact endpoints within a station/run: f006 uses its 0–6 h total, later leads
subtract the total six hours earlier, and missing endpoints/earlier leads remain
unavailable. Negative differences follow the archiver's nonnegative clipping policy.
The conversion occurs before date/lead filtering so an endpoint outside the plot
period is retained. Mixed old/new monthly schemas are handled per file. Cumulative
`precip_accum` is never scored as a six-hour amount by these model adapters.

REFS uses its already derived `precip_6h` distribution. Both models reuse the
existing six-hour duration and observation endpoint-tolerance matcher. Comparisons
use the same observation and shared targets, with existing reference offsets.

## Validation

Synthetic Parquet tests exercise both loaders, all four pages and all four elements,
separate wind/gust rows, custom roots, initialization-month boundaries, scheduled
departures versus missing members, strict versus inclusive events, probability
source/missingness, and legacy/mixed precipitation schemas. Production files remain
unchanged; a production smoke test should use the actual archive paths and dates.
