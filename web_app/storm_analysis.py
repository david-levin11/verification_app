"""Single-run, station-level storm diagnostics for point weather elements."""
import numpy as np
import pandas as pd
from comparison import prepare_forecasts
from config import get_percentile_columns, is_probabilistic, get_element_config
from pairing import build_verification_pairs, get_obs_value_column
from probability import forecast_probabilities, threshold_event

INTERVALS = [('25', '75'), ('10', '90'), ('5', '95')]


def observed_percentile(values, levels, observed):
    """Archived-quantile rank, with honest tail censoring and tied-value ranges."""
    x, p = np.asarray(values, dtype=float), np.asarray(levels, dtype=float)
    valid = np.isfinite(x) & np.isfinite(p)
    x, p = x[valid], p[valid]
    if (len(x) < 2 or np.any(np.diff(x) < 0) or np.any(np.diff(p) <= 0)
            or np.any((p <= 0) | (p >= 100))):
        return np.nan, np.nan, np.nan, 'Invalid/insufficient quantiles'
    if not np.isfinite(observed):
        return np.nan, np.nan, np.nan, 'No matched observation'
    if observed < x[0]:
        return float(p[0]), np.nan, float(p[0]), f'Below p{p[0]:g}'
    if observed > x[-1]:
        return float(p[-1]), float(p[-1]), np.nan, f'Above p{p[-1]:g}'
    equal = np.flatnonzero(x == observed)
    if len(equal):
        low, high = float(p[equal[0]]), float(p[equal[-1]])
        label = f'p{low:g}' if low == high else f'p{low:g}–p{high:g} (tied)'
        return (low + high) / 2, low, high, label
    right = np.searchsorted(x, observed, side='right')
    rank = float(p[right-1] + (p[right]-p[right-1]) *
                 (observed-x[right-1]) / (x[right]-x[right-1]))
    return rank, rank, rank, f'p{rank:.1f} (interpolated)'


def build_storm_cases(model_frame, observations, model, obs_source, element,
                      init_time, percentile=None, tolerance='1h', threshold=25, operator='>='):
    if element not in ['wind', 'gust', 'rh']:
        raise ValueError('Storm diagnostics currently support wind, gust, and RH.')
    prepared = prepare_forecasts(model_frame, model, element, percentile)
    if prepared.empty:
        return prepared
    init = pd.to_datetime(init_time, utc=True).tz_convert(None)
    prepared = prepared[prepared.init_time.eq(init)].copy()
    prepared = prepared.drop_duplicates(['station_id', 'valid_time'], keep='last')
    if prepared.empty:
        return prepared
    prepared['model_value'] = prepared.model_value.where(np.isfinite(prepared.model_value))
    reports = observations.copy()
    if not reports.empty:
        value_column = get_obs_value_column(reports, element)
        reports[value_column] = pd.to_numeric(reports[value_column], errors='coerce')
        reports = reports[np.isfinite(reports[value_column])].copy()
    pairs = (build_verification_pairs(prepared, reports, model, obs_source, element,
                                      percentile, tolerance) if not reports.empty else pd.DataFrame())
    columns = ['station_id', 'init_time', 'valid_time', 'obs_value', 'obs_valid_time',
               'obs_time_offset_minutes']
    if element == 'wind' and not pairs.empty:
        for column in get_element_config(element).get('direction_candidates', []):
            name = column + '_obs' if column + '_obs' in pairs else column
            if column in observations and name in pairs:
                pairs['observed_direction'] = pd.to_numeric(pairs[name], errors='coerce')
                columns.append('observed_direction')
                break
    if pairs.empty:
        result = prepared.copy()
        result['obs_value'] = np.nan
        result['obs_valid_time'] = pd.NaT
        result['obs_time_offset_minutes'] = np.nan
    else:
        result = prepared.merge(pairs[[c for c in columns if c in pairs]].drop_duplicates(
            ['station_id','init_time','valid_time'], keep='last'),
            on=['station_id','init_time','valid_time'], how='left', validate='one_to_one')
    result['obs_value'] = pd.to_numeric(result.obs_value, errors='coerce')
    result['obs_value'] = result.obs_value.where(np.isfinite(result.obs_value))
    result['error'] = result.model_value - result.obs_value
    result['absolute_error'] = result.error.abs()
    result['observed_event'] = threshold_event(result.obs_value, threshold, operator).astype(float)
    result.loc[result.obs_value.isna(), 'observed_event'] = np.nan
    result['median_value'] = result.model_value
    if is_probabilistic(model, element):
        columns = get_percentile_columns(element)
        available = [(col, float(p)) for p, col in columns.items() if col in result]
        numeric = result[[col for col, _ in available]].apply(pd.to_numeric, errors='coerce')
        ranks = [observed_percentile(row, [p for _, p in available], ob)
                 for row, ob in zip(numeric.to_numpy(), result.obs_value)]
        result[['observed_percentile','rank_low','rank_high','rank_label']] = pd.DataFrame(
            ranks, index=result.index, columns=['observed_percentile','rank_low','rank_high','rank_label'])
        # Rank validation must also apply when no observation is present.
        result['distribution_valid'] = [observed_percentile(row, [p for _, p in available], 0)[3]
            != 'Invalid/insufficient quantiles' for row in numeric.to_numpy()]
        result['forecast_probability'] = forecast_probabilities(result, element, threshold, operator)
        result['median_value'] = np.nan
        if columns['50'] in result:
            result['median_value'] = pd.to_numeric(result[columns['50']], errors='coerce')
        for low, high in INTERVALS:
            if columns[low] in result and columns[high] in result:
                a = pd.to_numeric(result[columns[low]], errors='coerce')
                b = pd.to_numeric(result[columns[high]], errors='coerce')
                valid = result.distribution_valid & np.isfinite(a) & np.isfinite(b) & a.le(b)
                result[f'width_{low}_{high}'] = (b-a).where(valid)
                result[f'inside_{low}_{high}'] = result.obs_value.between(a,b).astype(float).where(
                    valid & result.obs_value.notna())
    result['median_error'] = result.median_value - result.obs_value
    if 'forecast_direction' in result and 'observed_direction' in result:
        valid = (result.forecast_direction.between(0,360) & result.observed_direction.between(0,360)
                 & result.model_value.gt(0) & result.obs_value.gt(0))
        result['angular_error'] = (((result.forecast_direction-result.observed_direction+180) % 360)-180).abs().where(valid)
    return result.sort_values(['valid_time','station_id']).reset_index(drop=True)


def available_intervals(cases):
    return [(lo, hi) for lo, hi in INTERVALS if f'width_{lo}_{hi}' in cases]


def common_interval_cases(cases):
    widths = [f'width_{lo}_{hi}' for lo, hi in available_intervals(cases)]
    return cases.dropna(subset=['obs_value'] + widths)


def interval_summary(snapshot):
    """All reported interval widths/coverage use the same matched station cohort."""
    common = common_interval_cases(snapshot)
    rows = []
    for lo, hi in available_intervals(snapshot):
        width = common[f'width_{lo}_{hi}']
        rows.append(dict(interval=f'p{lo}–p{hi}', stations=len(common),
            mean_width=width.mean(), median_width=width.median(),
            inside_count=int(common[f'inside_{lo}_{hi}'].sum()),
            coverage_percent=100*common[f'inside_{lo}_{hi}'].mean()))
    return pd.DataFrame(rows)


def evolution_summary(cases, balanced=False):
    data = cases.copy()
    if balanced:
        eligible = common_interval_cases(data)
        counts = eligible.groupby('station_id').valid_time.nunique()
        stations = counts[counts.eq(data.valid_time.nunique())].index
        data = data[data.station_id.isin(stations)]
    rows = []
    for valid, part in data.groupby('valid_time', sort=True):
        paired = part.dropna(subset=['obs_value'])
        row = dict(valid_time=valid, forecast_hour=float(part.forecast_hour.iloc[0]),
                   forecast_stations=len(part), matched_stations=len(paired),
                   bias=paired.error.mean(), mae=paired.absolute_error.mean(),
                   rmse=np.sqrt((paired.error**2).mean()))
        common = common_interval_cases(part)
        row['interval_stations'] = len(common)
        for lo, hi in available_intervals(part):
            row[f'mean_width_{lo}_{hi}'] = common[f'width_{lo}_{hi}'].mean()
            row[f'coverage_{lo}_{hi}'] = 100*common[f'inside_{lo}_{hi}'].mean()
        rows.append(row)
    return pd.DataFrame(rows)
