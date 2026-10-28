# Model Comparison

Run the app as usual (`streamlit run web_app/app.py`, or `streamlit run app.py`
from `web_app`) and choose **Model Comparison** in the sidebar. Set the archive
root to the directory containing `ndfd/`, `nbm/`, `obs/`, etc.

## Suggested NDFD / NBM setup

- Model A: NDFD (the reference); Model B: NBM.
- Select wind, stations, valid-date range, and Model A's lead range.
- Enable **Offset Model B reference time relative to Model A**.
- Select -6 or -12 hours to use earlier NBM guidance.
- Reference tolerance is independent of observation tolerance. Set it to 0
  for exact reference matches, or permit a small difference for differently
  scheduled cycles (default ±1 hour). The paired-data preview shows actual
  references, forecast hours, offsets, and deviations from the requested offset.

An NDFD reference at June 1 00 UTC verifying June 2 00 UTC can match NBM from
May 31 18 UTC with a -6-hour offset. Their leads are 24 and 30 hours, and they
receive exactly the same observation. The lead filter applies to Model A;
Model B is not incorrectly restricted to Model A's forecast-hour list.

## Available forecast projections and day boundaries

The app no longer uses per-model archiver schedules as verification whitelists.
Map Explorer and Aggregate Verification filter continuous lead intervals selected
by the day controls. **Use all forecast hours** applies no lead filter. Every
archived 3-hour step (and irregular steps such as NBM's 5/11-hour leads) is eligible;
an absent increment simply contributes no row. Storm Specific likewise loads all
projections of the chosen run within the selected event dates.

Day 1 includes 0 through 24 hours. Day 2 is strictly greater than 24 through 48;
Day 3 is >48 through 72; and Day 7 is >144 through 168. Thus hour 24 belongs to
Day 1, hour 27 to Day 2, and hour 168 to Day 7, with no duplicated boundaries.
These are lead intervals independent of the forecast accumulation duration.

Model Comparison defaults to A leads 0–168 hours, with 3-hour adjustment steps.
It scores only shared station/verification targets under the requested reference
offset/tolerance. A 3-hourly A model and 6-hourly B model normally share the 6-hourly
targets; intermediate A rows are counted as unmatched. No missing B forecasts are
interpolated. Day-group charts use A's actual lead; B's actual lead is retained and
can differ with the offset. Existing station/date/window matching is unchanged.

All-hours queries derive the initialization-month lookback from cached Parquet
forecast-hour footer maxima, invalidated by file size/mtime changes. When those
statistics are absent, all eligible older archive months are included rather than
assuming a seven-day horizon. Comparison's bounded lookback derives from A's lead
limit plus the reference offset/tolerance and daily-target endpoint allowance.

## Reference-time matching

Each distinct A station/reference/target is a verification
case. Choose B's nearest reference to `A_reference + offset` within the reference
tolerance, requiring the same station and target. If absent, exclude and count
that case. This does not join every A run to every B run at the same valid time.

## Observations

Models are matched first; observations are paired once using A's target.
Both models use exactly that observation. Instantaneous reports use the nearest
station report within the selected tolerance (default 60 minutes); a :53 report
can match the next top of hour. Actual report times and signed offsets are saved.

Accumulation observations must have the configured 6/24/48/72-hour duration.
Their start and end must be within the observation tolerance of the model's
window. The observed amount is not shifted, interpolated, or prorated.
Daily temperatures follow the existing configured anchor-date convention.
The last archived observation per station/date is selected for temperature
pairing. Confirm that this convention matches the intended forecast windows.

The loader reads earlier initialization-month files and neighboring observation
months, accepts normalized and legacy NDFD per-element filenames, and includes
the whole sidebar end date. Gust observations can be read from the wind archive,
where the observation archiver stores them. Configured capabilities do not guarantee that the
requested files or percentile columns are present locally.

## Scores and displays

- Point scorecard: bias, MAE, RMSE, POD, FAR, CSI, and frequency bias.
- Bias is better nearer zero; frequency bias nearer one. Other error measures
  are lower-is-better; POD and CSI higher-is-better.
- Lead-day curves use A's actual lead, with B's actual lead retained in the data.
- Station differences have a zero-centered blue/orange scale. Positive advantage
  means A is better. Metadata is optional; coordinates are required for the map.
- Observed-category and monthly breakdowns describe conditions; overall event
  scores still include non-events and false alarms.
- Counts and raw paired cases can be reviewed and downloaded as CSV.
- Optional paired MAE confidence intervals resample complete target-day blocks,
  keeping all stations and runs on that day together. Require at least five days;
  dependence across days and short samples limit interpretation.

Probability-capable models use separate point percentiles (default p50). If only
one model is probabilistic, its probability scores/reliability are shown alone;
no distribution score is assigned to the deterministic model. When both are
probabilistic, Brier and reliability scores use the intersection of valid
probability cases. Point metrics retain all common point cases. `n_prob` shows
any smaller probability sample. The shared approximation rules from
VERIFICATION_CHANGES.md apply, including tails, ties, and crossing quantiles.

## Wind-speed subsets and direction verification

For the wind element, **Set a minimum observed speed for wind-speed verification**
is optional and off by default. It retains cases with observed speed greater
than or equal to the selected cutoff. Both models, all wind-speed scorecards,
plots, probability diagnostics, confidence intervals, and speed-case downloads
use that same retained subset. Counts show how many shared cases the filter
excludes. This conditions verification on observed wind: it excludes false
alarms during lighter observed winds, so unfiltered scores remain useful.

**Verify wind direction** is a separate optional control, off by default. Its
minimum observed speed defaults to 5 kt, independently of the wind-speed score
cutoff. The angular-error threshold defaults to 45 degrees. Direction uses the
shared forecast-reference/target matching, offset, observation tolerance, and
optional observed-direction sector filter already selected on the page. Speed
and direction come from the same matched observation report; direction is not
matched separately to a different report.

Forecast directions are recognized through the wind configuration's
`forecast_direction_candidates` (`wind_dir_deg`, then `wind_direction`).
Observation direction uses the existing observation candidates. If either
forecast or the observation archive lacks direction, the page explains the
missing source and continues speed/probability verification. Speed percentiles
alone do not provide a forecast direction distribution. NBM and NDFD samples
include direction; the supplied NBM QMD sample does not. Other configured wind
models use the same field detection.

Directions must be finite and between 0 and 360 degrees; 360 is normalized to
north (0). Sentinel/out-of-range values are excluded. Direction verification
uses the intersection of valid directions and positive observed/forecast speeds
for both models, subject to its observed-speed minimum. A zero-speed forecast
has no defined direction; it remains eligible for wind-speed scoring. The page
reports sequential exclusion counts for invalid directions, low/calm observed
winds, and nonpositive forecast speeds.

Absolute angular error is `abs(((forecast - observed + 180) % 360) - 180)`,
ranging from 0 to 180 degrees. The scorecard reports mean and median absolute
angular error and the percentage with error **strictly greater** than the chosen
threshold. Thus an error exactly equal to 45 degrees does not exceed 45.
Differences in percentages are percentage points. All three metrics are better
when smaller; the comparison does not establish statistical significance.

Displays include exceedance curves, 15-degree error histograms, lead-day curves,
station difference maps/tables, and shared paired direction data. Direction cases
and scorecards can be downloaded separately; scorecards include sample counts
and the error threshold. Direction results can remain available even if a
stricter speed-score cutoff removes all speed-verification cases. After changing
inputs, click **Run Model Comparison** to refresh; existing results continue to
use their saved settings.

## Tests

`python -m pytest tests -q`

Tests use synthetic archives and Streamlit AppTest, covering offsets across a
month boundary, actual lead differences, distinct targets/stations, duplicate
keys, sparse probabilities, :53 reports, accumulation duration, daily extrema,
score orientation, missing matches, and mixed/two-probabilistic
page flows. Wind tests also cover circular errors, sentinel values, common
direction-case selection, calm winds, independent minimum-speed filters,
probability sample consistency, missing direction fields, station maps, empty
subsets, and saved page settings. No NOAA downloads or real archive writes occur during tests.

Gust verification now supports dedicated and combined wind/gust archives across
all pages, with missing-report coverage and optional observed-gust minimums. See
[GUST_VERIFICATION.md](GUST_VERIFICATION.md) for source priority and timing assumptions.
