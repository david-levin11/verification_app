"""Read two forecast archives and one observation archive for comparison."""
from datetime import date, datetime
from pathlib import Path
import duckdb
import pandas as pd
from config import (get_model_pair_date_column, get_obs_filter_time_column,
                    get_obs_time_column, get_pairing_method)


def date_bounds(start, end):
    start, finish = pd.Timestamp(start), pd.Timestamp(end)
    if isinstance(end, date) and not isinstance(end, datetime):
        finish += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    if start > finish:
        raise ValueError('Start date must not be after end date')
    return start, finish


def archive_paths(root, model, element, start, end):
    """Prefer normalized files, accepting legacy per-element NDFD filenames."""
    paths, missing = [], []
    for month in pd.period_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq='M'):
        folder = Path(root) / model / element
        names = [f'{month.year}_{month.month:02d}_archive.parquet',
                 f'{month.year}_{month.month:02d}_{model}_{element}_archive.parquet']
        found = next((folder / n for n in names if (folder / n).is_file()), None)
        if found:
            paths.append(str(found))
        else:
            missing.append(str(folder / names[0]))
    return paths, missing


def load_comparison_data(root, model_a, model_b, obs, element, start, end,
                         stations, lookback_hours=240, obs_time_tolerance='1h'):
    """Dates select forecast targets; look back for initialization-month files.

    Load observations once. Older source months are necessary when a target in
    the first days of a month is forecast by a run from the previous month.
    """
    if not stations:
        raise ValueError('Select at least one station')
    start, end = date_bounds(start, end)
    tolerance = pd.Timedelta(obs_time_tolerance)
    if tolerance < pd.Timedelta(0):
        raise ValueError('Observation time tolerance must be non-negative')
    warnings = []
    def query(model, observation=False):
        if observation:
            padding = tolerance if get_pairing_method(element) == 'time' else pd.Timedelta(0)
            lo, hi = start - padding, end + padding
            read_start = lo
        else:
            lo, hi = start, end
            read_start = start - pd.Timedelta(hours=lookback_hours)
        files, missing = archive_paths(root, model, element, read_start, hi)
        if not files and observation and model == 'obs' and element == 'gust':
            # The observation archiver writes gusts alongside sustained wind.
            files, missing = archive_paths(root, model, 'wind', read_start, hi)
            if files:
                warnings.append('OBS gust: using gust columns from the wind observation archive.')
        if not files:
            raise ValueError(f'No {model.upper()} {element} archive files were found under {root}')
        if missing:
            warnings.append(f'{model.upper()}: {len(missing)} requested monthly file(s) unavailable; using {len(files)} file(s).')
        with duckdb.connect() as connection:
            schema = connection.execute('SELECT * FROM read_parquet(?, union_by_name=true) LIMIT 0', [files]).df()
            station_column = 'station_id' if 'station_id' in schema else 'stid'
            time_column = (get_obs_filter_time_column(element) if observation else
                           get_model_pair_date_column(element) if get_pairing_method(element) == 'date' else 'valid_time')
            if station_column not in schema or time_column not in schema:
                raise ValueError(f'{model.upper()} archive lacks station ID or {time_column}')
            # Identifiers come from fixed config/schema; values and paths are bound parameters.
            statement = (f'SELECT * FROM read_parquet(?, union_by_name=true) '
                         f'WHERE "{station_column}" IN (SELECT unnest(?)) '
                         f'AND "{time_column}" BETWEEN ? AND ?')
            frame = connection.execute(statement, [files, stations, lo.to_pydatetime(), hi.to_pydatetime(warn=False)]).df()
        if observation:
            time_column = get_obs_time_column(element)
            if time_column not in frame:
                raise ValueError(f'{model.upper()} archive lacks {time_column}')
            frame['valid_time'] = frame[time_column]
        return frame
    return query(model_a), query(model_b), query(obs, True), warnings
