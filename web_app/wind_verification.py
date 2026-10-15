"""Verification of paired wind directions and observed-speed subsets."""
import numpy as np
import pandas as pd

DIRECTION_LABELS = {'angular_mae': 'Mean absolute angular error (°)',
    'angular_median': 'Median absolute angular error (°)',
    'exceedance_percent': 'Angular error exceeding threshold (%)'}


def normalize_direction(values):
    """Reject missing/sentinel directions; 360 and 0 both mean north."""
    numeric = pd.to_numeric(values, errors='coerce')
    return numeric.where(np.isfinite(numeric) & numeric.between(0, 360)) % 360


def absolute_angular_error(forecast, observed):
    return ((normalize_direction(forecast) - normalize_direction(observed) + 180) % 360 - 180).abs()


def filter_observed_speed(cases, minimum=None):
    if minimum is None:
        return cases.copy()
    if not np.isfinite(minimum) or minimum < 0:
        raise ValueError('Minimum observed wind speed must be finite and non-negative')
    if cases.empty:
        return cases.copy()
    speed = pd.to_numeric(cases.obs_value, errors='coerce')
    return cases.loc[np.isfinite(speed) & speed.ge(minimum)].copy()


def filter_observed_sector(cases, lower, upper):
    if cases.empty:
        return cases.copy()
    if 'observed_direction' not in cases:
        raise ValueError('The paired observations have no wind direction field')
    direction = normalize_direction(cases.observed_direction)
    if lower == 0 and upper == 360:
        mask = direction.notna()
    else:
        lower, upper = lower % 360, upper % 360
        mask = direction.between(lower, upper) if lower <= upper else (direction.ge(lower) | direction.le(upper))
    return cases.loc[mask].copy()


def direction_cases(cases, minimum_observed_speed=5.):
    """Use the same valid direction cases for A and B, independently of speed scoring.

    Directions attached to calm forecasts or observations are undefined and are
    excluded here, while remaining eligible for the wind-speed verification.
    """
    if not np.isfinite(minimum_observed_speed) or minimum_observed_speed < 0:
        raise ValueError('Minimum observed wind speed must be finite and non-negative')
    result = cases.copy()
    required = ['a_forecast_direction', 'b_forecast_direction', 'observed_direction']
    missing = [c for c in required if c not in result]
    diagnostics = dict(input_cases=len(cases), missing_fields=missing,
        invalid_directions=0, below_observed_minimum_or_calm=0,
        nonpositive_forecast_speed=0, direction_cases=0)
    if missing or result.empty:
        return result.iloc[:0].copy(), diagnostics
    for col in required:
        result[col] = normalize_direction(result[col])
    valid = result[required].notna().all(axis=1)
    diagnostics['invalid_directions'] = int((~valid).sum())
    result = result.loc[valid].copy()
    obs_speed = pd.to_numeric(result.obs_value, errors='coerce')
    valid = np.isfinite(obs_speed) & obs_speed.gt(0) & obs_speed.ge(minimum_observed_speed)
    diagnostics['below_observed_minimum_or_calm'] = int((~valid).sum())
    result = result.loc[valid].copy()
    a_speed = pd.to_numeric(result.a_model_value, errors='coerce')
    b_speed = pd.to_numeric(result.b_model_value, errors='coerce')
    valid = np.isfinite(a_speed) & np.isfinite(b_speed) & a_speed.gt(0) & b_speed.gt(0)
    diagnostics['nonpositive_forecast_speed'] = int((~valid).sum())
    result = result.loc[valid].copy()
    for side in ['a', 'b']:
        result[f'{side}_angular_error'] = absolute_angular_error(
            result[f'{side}_forecast_direction'], result.observed_direction)
    diagnostics['direction_cases'] = len(result)
    return result, diagnostics


def direction_scores(cases, threshold=45):
    if not np.isfinite(threshold) or not 0 <= threshold <= 180:
        raise ValueError('Angular error threshold must be between 0 and 180 degrees')
    rows = []
    for metric, label in DIRECTION_LABELS.items():
        values = []
        for side in ['a', 'b']:
            errors = cases[f'{side}_angular_error'] if not cases.empty else pd.Series(dtype=float)
            value = (errors.mean() if metric == 'angular_mae' else errors.median()
                     if metric == 'angular_median' else errors.gt(threshold).mean() * 100)
            values.append(float(value))
        a, b = values
        better = ('Unavailable' if not (np.isfinite(a) and np.isfinite(b)) else
                  'Tie' if np.isclose(a, b) else 'A' if a < b else 'B')
        rows.append(dict(metric=metric, label=label, a=a, b=b, difference=a-b, better=better,
                         n=len(cases), error_threshold_degrees=threshold))
    return pd.DataFrame(rows)


def direction_exceedance(cases, thresholds=None):
    thresholds = np.arange(181) if thresholds is None else np.asarray(thresholds)
    if not np.isfinite(thresholds).all() or ((thresholds < 0) | (thresholds > 180)).any():
        raise ValueError('Angular thresholds must be between 0 and 180 degrees')
    table = pd.DataFrame({'threshold': thresholds})
    for side in ['a', 'b']:
        errors = cases[f'{side}_angular_error'].to_numpy() if not cases.empty else np.array([])
        table[side] = ((len(errors) - np.searchsorted(np.sort(errors), thresholds, side='right')) * 100 / len(errors) if len(errors)
                       else np.full(len(thresholds), np.nan))
    table['n'] = len(cases)
    return table


def grouped_direction_scores(cases, group, threshold=45):
    tables = []
    for name, part in cases.groupby(group, observed=True, sort=True):
        scores = direction_scores(part, threshold)
        scores[group] = name
        scores['n'] = len(part)
        tables.append(scores)
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(
        columns=['metric', 'label', 'a', 'b', 'difference', 'better', group, 'n'])
