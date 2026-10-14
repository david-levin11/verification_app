# Shared probability verification and observation matching

Branch: model-comparison, based on refactor-multi-element.

## Thresholds

Map Explorer and Aggregate Verification share an event definition control:
`>=`, `>`, `<=`, or `<`. RH and minimum temperature default to `<=`; other
elements default to `>=`. Forecast categories retain their configured bins.

## Probability approximation

`web_app/probability.py` supplies threshold probabilities, reliability tables,
Brier scores and reliability error to both metrics and plotting code.

- Interpolate the CDF linearly between distinct archived quantiles.
- Beyond the available quantiles, hold the nearest percentile probability;
  with p5/p95 this uses 5%/95% CDF tails. These are explicit approximations,
  not recovered tail distributions or exact probabilities.
- At tied quantiles, use the lower jump edge for `<` and the upper edge for
  `<=`; obtain `>=` and `>` by the appropriate complement.
- Approximate all-equal quantiles as a point mass, retaining zero-event cases.
- Exclude crossing quantiles instead of sorting away the problem. At least
  two finite quantiles are required; `n_prob` reports the score's sample size.
- Reliability error is the sample-weighted squared difference between mean
  probability and observed frequency in 10% probability bins. It is a binned
  calibration diagnostic, distinct from the overall Brier score.

Scores and plots share these assumptions. Quantile histograms remain a
separate diagnostic; ties in discrete precipitation/snow do not imply the
continuous-data expected bin frequencies should hold exactly.

## Observation matching

The sidebar tolerance is in minutes (default 60; 0 requires exact times).
Instantaneous observations match the nearest station report. A :53 report
can match the following top-of-hour forecast. Actual observation timestamps
and signed offsets in minutes are retained in paired data.

Accumulations require matching durations (6, 24, 48 or 72 hours) and allow
both window endpoints to differ from the forecast window by the selected
tolerance. The amount is not shifted, prorated, or recomputed. Observation
start/end fields are required; mismatched durations are excluded before
nearest-time matching. Daily temperatures continue to pair by configured
anchor date, keeping the last observation for each station/date.

The loader pads observation reads by the tolerance, including neighboring
monthly files when available. Sidebar end dates include the whole day.

## Validation

Run `python -m pytest tests/test_verification.py -q` with the app dependencies
and pytest installed. Tests cover scores, equality, tails, ties, time/window
matching, month boundaries, and Streamlit controls.

The Model Comparison page now uses these shared utilities. See
MODEL_COMPARISON.md for reference matching, offsets, observation pairing,
probabilistic sample selection, and archive limitations.
