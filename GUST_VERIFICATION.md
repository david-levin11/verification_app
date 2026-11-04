# Gust verification

Select `gust` as the element in Map Explorer, Aggregate Verification, Storm
Specific Zoom, or Model Comparison. Gust is configured for NBM, experimental
NBM, HRRR, NDFD, NBM QMD, experimental NBM QMD, and URMA. The configured
capability still requires gust columns to exist in the local archive. Combined
wind/gust models use their wind forecast-hour configuration. NDFD and QMD retain
their dedicated gust forecast-hour configurations.

## Archive layouts

All pages use `archive_files.resolve_archive_paths`. For each requested model,
element, and month it checks:

1. `model/{source}/gust/YYYY_MM_archive.parquet`.
2. The legacy filename `YYYY_MM_{source}_gust_archive.parquet` in that folder.
3. Gust columns in `model/{source}/wind/YYYY_MM_archive.parquet`, including the
   corresponding legacy wind filename.

Exactly one usable file is selected per month. A valid dedicated gust file has
priority over the wind file; missing values in that file are not filled from a
second archive. Different months may use different layouts. No files need to be
reorganized, copied, or renamed for the app.

Schema checks require a configured gust column: `wind_gust_kt` or `i10fg` for
point forecasts, `gust_p5` through `gust_p95` for QMD (requested percentiles must
be available), and `obs_wind_gust_kts` or `wind_gust_kt` for verification sources.
Sustained wind columns cannot supply gust verification. Files without any gust
value columns are skipped with an explanation; if no usable source exists,
the page reports missing gust data. An all-null gust column is a valid schema,
but supplies no usable pairs.

Monthly reads use schemas combined by column name, allowing dedicated gust
files and combined wind/gust files to have different optional columns. Reads
include preceding forecast-initialization months when needed. File paths and
station values are bound query parameters, including paths with spaces/quotes.

## Verification, missing observations, and timing

Point gusts use the existing bias, MAE, RMSE, threshold, category, station-map,
and aggregate diagnostics. QMD gust percentiles support the existing Brier,
reliability, and quantile diagnostics. Model Comparison retains shared
forecast/observation cases, reference offsets, and probability-case rules.

Missing or nonfinite gusts are excluded during pairing; explicitly recorded
zero gusts remain valid. The pages report missing gust observation counts among
loaded reports. Map Explorer and Aggregate Verification retain that coverage
message with their saved results. Missing reports are not interpreted as calm
conditions. Missing gust reporting can affect the representativeness of scores,
especially where gusts are only reported under particular conditions.

Gust matching uses the recorded valid/report timestamp, with the selected
nearest-report tolerance for station observations and exact analysis-time
matching for URMA. The supplied gust archives do not include explicit gust
measurement/maximum-period windows. The app does not infer, shift, or recompute
hourly maximum gusts or establish that model and observation gust periods are
identical. Storm plots display the actual observation timestamps.

Map Explorer, Aggregate Verification, and Model Comparison provide an optional
minimum observed-gust filter, off by default. When enabled, it uses `gust >=
minimum`, applies the same subset to both models, and reports excluded paired
cases. All corresponding scores, probability diagnostics, plots, and case
exports use the retained subset. This conditions scores on observed gusts and
excludes false alarms during lighter observed gusts; unfiltered scores remain
useful. Filtering does not alter the raw Storm Specific Zoom time series.

Gust direction is not a separate direction-verification product. The existing
optional observed-wind-direction sector filter can describe gust conditions
where observed direction is available. The optional circular direction scorecard
remains specific to sustained wind.

## Storm plots

Storm Specific Zoom selects gust values, gust percentile bands, and gust units
from the element configuration. Its point percentile follows the user's
selection. Missing observational gusts appear as gaps, while recorded zeros
remain plotted. Nonfatal archive/coverage warnings do not suppress the plot.
An unavailable gust column produces an error instead of falling back to a
sustained-wind column. The final plot date includes the entire day.

## Validation

Run `python -m pytest tests -q`. The synthetic gust tests cover both layouts,
month-by-month fallback and dedicated-file priority, legacy names, differing
schemas, prior initialization months, zero/missing/nonfinite values, recorded
report offsets, exact URMA times, QMD probabilities and selected-percentile storm
plots, archive paths containing quotes, and all four Streamlit page flows.

The supplied NBM/HRRR/URMA combined archives, QMD gust-percentile file, corrected
NDFD gust file, and observation file established the schemas. A small real-file
loading check also confirmed that missing Juneau gust reports produce no gust
pairs rather than fabricated zeros; no model-performance conclusion was drawn.
