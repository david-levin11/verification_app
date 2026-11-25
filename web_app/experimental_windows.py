"""Validate archived experimental extrema and their observation windows."""

import pandas as pd
from config import EXPERIMENTAL_NATIVE_ELEMENTS


def prepare_experimental_extrema(frame, element, observation=False):
    if frame.empty:
        return frame
    required = {'window_start', 'window_end', 'valid_time'}
    if observation:
        required.add('coverage_ok')
    if missing := required.difference(frame.columns):
        raise ValueError(f"Experimental extrema archive lacks {', '.join(sorted(missing))}.")
    frame = frame.copy()
    for column in ('window_start', 'window_end', 'valid_time'):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors='coerce').dt.tz_convert(None)
    start, end = frame.window_start, frame.window_end
    valid = end.gt(start) & frame.valid_time.eq(end)
    if element not in EXPERIMENTAL_NATIVE_ELEMENTS:
        start_hour = 12 if element == 'maxt' else 0
        valid &= (end - start).eq(pd.Timedelta(hours=12))
        valid &= start.eq(start.dt.normalize() + pd.Timedelta(hours=start_hour))
    if observation:
        valid &= frame.coverage_ok.eq(True)
    return frame.loc[valid].copy()
