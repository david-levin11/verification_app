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

## Two matching methods

**Reference times**: each distinct A station/reference/target is a verification
case. Choose B's nearest reference to `A_reference + offset` within the reference
tolerance, requiring the same station and target. If absent, exclude and count
that case. This does not join every A run to every B run at the same valid time.

**Common reference cutoff**: choose the latest archived A reference at/before
one UTC cutoff per station/target, and the latest B reference at/before
`cutoff + offset`. Lead filtering follows selection. This mode does not prove
that the forecasts had been published by those times.

## NDFD archive interpretation

In `alaska_verification/utils.py`, `process_file_pair()` archives cfgrib
`valid_time` and the decoded GRIB `step` as `forecast_hour`. Reconstructing
`valid_time - forecast_hour` recovers the GRIB reference time. The archiver's
filename selection uses snapshots at hours 11 and 23, but file publication
and retrieval times are not retained in each row. A reference time is therefore
not a verified editing time or an identification of the NBM run used by a
forecaster.

Duplicate station/reference/target rows keep the last row in archive input
order. Because historical file extraction used asynchronous completion, this
cannot establish which duplicate was the latest published human forecast.
The requested offset remains an explicit user assumption.

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

## Tests

`python -m pytest tests/test_comparison.py tests/test_verification.py -q`

Tests use synthetic archives and Streamlit AppTest, covering offsets across a
month boundary, actual lead differences, distinct targets/stations, duplicate
keys, sparse probabilities, :53 reports, accumulation duration, daily extrema,
cutoff selection, score orientation, missing matches, and mixed/two-probabilistic
page flows. No NOAA downloads or real archive writes occur during tests.
