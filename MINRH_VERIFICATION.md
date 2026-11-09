# Minimum relative humidity verification

MinRH is a separate element from instantaneous RH in all four pages. Supported
forecast models are **NBM** and **NDFD**, both deterministic. Select `minrh` in the
Element control. There is no percentile selector or probabilistic MinRH scoring.
The NBM field comes from scalar QMD output but is archived under NBM, not NBMQMD.
NBM MinRH run-hour options are 00Z and 12Z. NDFD retains all reference-hour options.

Source contract: alaska_verification branch `ndfd-minrh`, revision
`87994f645f14ecdf5608d90303a3c471d94fc50f`, particularly
[BACKFILLS.md](https://github.com/david-levin11/alaska_verification/blob/87994f645f14ecdf5608d90303a3c471d94fc50f/BACKFILLS.md),
`obs_minrh.py`, and `nbm_deterministic.py`.

## Archives and dates

Using the existing administrator-configured model archive root:

```text
nbm/minrh/YYYY_MM_archive.parquet
ndfd/minrh/YYYY_MM_archive.parquet
obs/minrh/YYYY_MM_archive.parquet
```

Values are percentages in `minrh`. Observation months and plot dates refer to
the **06Z endpoint day**. For example, May 1 06Z verifies the full minimum over
April 30 18Z through May 1 06Z. The archiver uses reports in the half-open
interval [18Z,06Z), preserving selected-sensor and reporting-coverage diagnostics.
There is no fallback to instantaneous RH, percentile RH, or native-period
experimental files. Missing archives remain missing.

NDFD must have explicit `window_start` and `window_end`. NBM's validated scalar
12-hour interval can reconstruct those bounds from `valid_time` only if neither
bound is present. Explicit bounds must describe exactly 12 hours ending at 06Z,
and `valid_time` must equal `window_end`. `window_hours`, if present, must be 12.
Rows flagged `window_duration_mismatch` are excluded. In particular a native
NDFD 00Z–06Z first period is never expanded into a previous-day 18Z–06Z forecast.

## Observations and matching

Observations require explicit window bounds and `coverage_ok=True`. Sparse rows
with false/missing coverage, invalid percentages, and incompatible periods are
excluded with loader warnings. A missing `coverage_ok` column is a schema error;
use the MinRH archiver output. Coverage is based on the archiver's maximum report
gap (normally 90 minutes, including both boundaries), not proof of a continuously
measured minimum. Real 0% values remain valid. Only percentages from 0 through
100 are accepted; if `rh_units` is present, it must be `%`.

The shared window-matching machinery checks duration before endpoint/start
matching. The observation-tolerance control remains available; it cannot make
a shortened or shifted native period comparable to the required daily window.
Comparison reference offsets and tolerances remain independent of observation
matching. Both models must supply an eligible forecast for the same station and
window before receiving the same matched observation. Files from previous
initialization months are included for targets crossing month boundaries.

## Metrics and plots

The default event is **MinRH <= 30%**. Other thresholds and comparison directions
remain selectable. Bias, MAE, RMSE, and categorical scores use the existing shared
metric functions. RH differences are percentage points, not relative percent
changes. Positive bias means a forecast minimum that is too high/moist.

Storm maps show forecast, observation, signed error, or absolute error. Station
details display forecast/observation points and their 12-hour windows, with RH
axes constrained to 0–100%. No distribution spread is invented for deterministic
guidance. Retained observation coverage diagnostics are included in paired data.

Synthetic tests cover all four pages, percent bounds, true zeros, clipped NDFD
periods, sparse observations, reference matching, low-RH event direction, and
month boundaries. A production MinRH archive test is still needed before rollout.
