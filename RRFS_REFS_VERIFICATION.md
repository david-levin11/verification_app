# RRFS and derived REFS verification

RRFS control and REFS support wind, gust, RH and six-hour precipitation in Map
Explorer, Aggregate Verification, Storm Zoom (including two-model overlays), and
Model Comparison. Snow and instantaneous temperature are not enabled by this change.

## Archive locations

The administrator-configured `archive_root` contains `rrfs/{element}/YYYY_MM_archive.parquet`
and the normal observation directories. RRFS gusts use the combined wind archive
when no dedicated gust archive exists. Direction verification uses RRFS archived
directions; REFS speed percentiles do not imply a forecast wind direction.

The administrator sets `refs_root` in the `[local]` section of
`.streamlit/secrets.toml` to the directory containing the REFS element folders.
If omitted, it defaults to `derived/refs` beside the model root. For example,
model root `/data/model` implies `/data/derived/refs`. An independent derived
location can be configured, and the same setting applies to every page; visitors
cannot change paths in the sidebar. See [LOCAL_CONFIGURATION.md](LOCAL_CONFIGURATION.md).
Source/derived archives are read-only inputs; no copying or reformatting is required.

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
operator. Point scores use the fixed selected percentile. REFS p25–p75 and p5–p95 shaded bands
still show the distribution, and deterministic RRFS uses points.

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

### Storm station wind/gust plumes

REFS Station detail places p25–p75 and p5–p95 shaded bands, boundary lines and p50 medians on
an actual UTC time axis. Small red points show every finite observation for the
selected station within the requested plot dates, including reports between
forecast steps. Larger red markers identify observations used for verification
and use their archived report timestamps when available. Date selections include
the entire end date; the full-report overlay excludes reporting-tolerance padding.
Zeros remain valid, other stations are excluded, and missing reports stay missing.
No hourly aggregation or resampling removes reports.

This overlay also applies to the shared-case comparison plot when REFS is A or B.
The comparison's forecast bands and score markers still use shared matched cases;
the extra observed points provide event context only. Matching tolerances,
completeness, scores and downloaded verification cases are unchanged. NBMQMD
uses the same shaded style and full wind/gust report overlay. Precipitation and
temperature measurement windows remain visible in their separate strips.

Synthetic Parquet tests exercise both loaders, all four pages and all four elements,
separate wind/gust rows, custom roots, initialization-month boundaries, scheduled
departures versus missing members, strict versus inclusive events, probability
source/missingness, and legacy/mixed precipitation schemas. Production files remain
unchanged; a production smoke test should use the actual archive paths and dates.

