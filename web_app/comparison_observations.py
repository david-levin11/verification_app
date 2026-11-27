"""Shared daily observations for comparisons across different archived periods."""

import numpy as np
import pandas as pd

from config import get_obs_filter_time_column, get_obs_time_column
from pairing import get_obs_value_column


def attach_date_aligned_observations(matched, observations, element, source):
    if matched.empty or observations.empty:
        return matched.iloc[:0].copy()

    # Legacy temperature observations already have a verification date.
    # The alternate archives store timestamp bounds in endpoint-month files.
    date_column = get_obs_filter_time_column(element, source)
    time_column = get_obs_time_column(element)
    value_column = get_obs_value_column(observations, element)
    station_column = 'station_id' if 'station_id' in observations else 'stid'
    reports = pd.DataFrame({
        'station_id': observations[station_column].astype('string').str.strip(),
        'target_time': pd.to_datetime(observations[date_column], utc=True).dt.tz_convert(None).dt.normalize().astype('datetime64[ns]'),
        'obs_value': pd.to_numeric(observations[value_column], errors='coerce'),
        'obs_valid_time': pd.to_datetime(observations[time_column], utc=True).dt.tz_convert(None),
    })
    for edge in ('start', 'end'):
        column = f'window_{edge}'
        values = observations[column] if column in observations else pd.Series(pd.NaT, index=observations.index)
        reports[f'obs_window_{edge}'] = pd.to_datetime(values, utc=True).dt.tz_convert(None)

    eligible = np.isfinite(reports.obs_value)
    if source != 'obs':
        eligible &= reports.obs_window_end.gt(reports.obs_window_start)
    if element == 'minrh':
        eligible &= reports.obs_value.between(0, 100)
    if 'coverage_ok' in observations:
        eligible &= observations.coverage_ok.eq(True)
    elif element == 'minrh' or source != 'obs':
        raise ValueError('The selected observation archive lacks its coverage_ok field.')
    reports = reports.loc[eligible].dropna(subset=['station_id', 'target_time', 'obs_valid_time'])

    if source == 'obs_exp':
        # A native archive can contain a nominal period plus unusual/partial windows.
        # Choose once per station/day, independently of which forecast is A or B.
        hour, duration = {'maxt': (14, 15), 'mint': (2, 18), 'minrh': (12, 18)}[element]
        length = reports.obs_window_end - reports.obs_window_start
        nominal = reports.obs_window_start.eq(
            reports.obs_window_start.dt.normalize() + pd.Timedelta(hours=hour)
        ) & length.eq(pd.Timedelta(hours=duration))
        reports = reports.assign(_nominal=nominal, _duration=length).sort_values(
            ['_nominal', '_duration', 'obs_valid_time'], kind='stable', na_position='first'
        ).drop(columns=['_nominal', '_duration'])

    keys = ['station_id', 'target_time']
    reports = reports.drop_duplicates(keys, keep='last')
    return matched.merge(reports, on=keys, how='inner', validate='many_to_one').assign(
        obs_source=source, period_alignment='verification_date'
    )
