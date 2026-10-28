"""Shared monthly archive discovery, including combined wind/gust archives."""
from pathlib import Path
from functools import lru_cache
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from config import get_element_config, get_percentile_columns, is_probabilistic


@lru_cache(maxsize=2048)
def _maximum_file_lead(path, size, modified_ns):
    """Footer statistics only; size/mtime invalidate cached metadata on append."""
    with pq.ParquetFile(path) as file:
        index=file.schema_arrow.get_field_index('forecast_hour')
        if index<0 or not file.metadata.num_row_groups:return None
        maximum=0.
        for group in range(file.metadata.num_row_groups):
            statistics=file.metadata.row_group(group).column(index).statistics
            if statistics is None or not statistics.has_min_max:return None
            value=float(statistics.max)
            if not np.isfinite(value) or value<0:return None
            maximum=max(maximum,value)
        return maximum


def forecast_archive_lookback(root,model,element,start,end):
    """Discover maximum archived lead without loading forecast rows.

    If any footer lacks lead statistics, include every eligible older archive
    month instead of guessing a horizon and silently losing long forecasts.
    """
    maximum=0.;earliest=None;unknown=False
    for source in ([element,'wind'] if element=='gust' else [element]):
        for path in (Path(root)/model/source).glob('*.parquet'):
            month=path.name[:7]
            if path.name not in [f'{month}_archive.parquet',f'{month}_{model}_{source}_archive.parquet']:continue
            try:month_start=pd.Timestamp(month.replace('_','-')+'-01')
            except ValueError:continue
            if month_start>pd.Timestamp(end):continue
            earliest=month_start if earliest is None else min(earliest,month_start)
            stat=path.stat()
            lead=_maximum_file_lead(str(path),stat.st_size,stat.st_mtime_ns)
            if lead is None:unknown=True
            else:maximum=max(maximum,lead)
    if unknown and earliest is not None:
        maximum=max(maximum,(pd.Timestamp(start)-earliest).total_seconds()/3600)
    return max(0.,maximum)


def resolve_archive_paths(root, model, element, start, end, observation=False):
    """Choose one source per month; a valid dedicated gust file takes priority.

    Validate gust schemas before falling back to wind files. Missing gusts in a
    valid archive stay missing; do not fill them from a second source.
    """
    files, missing, warnings, fallback = [], [], [], []
    cfg = get_element_config(element)
    if observation:
        gust_columns = cfg.get('obs_value_candidates', [])
    elif is_probabilistic(model, element):
        gust_columns = list(get_percentile_columns(element).values())
    else:
        gust_columns = cfg.get('model_value_candidates', [])
    for month in pd.period_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq='M'):
        found = None
        for source_element in ([element, 'wind'] if element == 'gust' else [element]):
            folder = Path(root) / model / source_element
            names = [f'{month.year}_{month.month:02d}_archive.parquet',
                     f'{month.year}_{month.month:02d}_{model}_{source_element}_archive.parquet']
            for name in names:
                path = folder / name
                if not path.is_file():
                    continue
                if element == 'gust':
                    columns = pq.ParquetFile(path).schema_arrow.names
                    if not any(c in columns for c in gust_columns):
                        warnings.append(f'{model.upper()} gust: skipped {path}; no gust value columns.')
                        continue
                found = str(path)
                if element == 'gust' and source_element == 'wind':
                    fallback.append(found)
                break
            if found:
                break
        if found:
            files.append(found)
        else:
            missing.append(str(Path(root)/model/element/f'{month.year}_{month.month:02d}_archive.parquet'))
    if fallback:
        warnings.append(f'{model.upper()} gust: using gust columns from the wind archive ({len(fallback)} monthly file(s)).')
    return files, missing, warnings


def gust_observation_coverage(frame):
    """Report missing gusts without converting them to zero or changing reports."""
    column = next((c for c in get_element_config('gust')['obs_value_candidates'] if c in frame), None)
    if column is None or frame.empty:
        return None
    values = pd.to_numeric(frame[column], errors='coerce')
    finite = np.isfinite(values)
    missing = int((~finite).sum())
    if not missing:
        return None
    zeros = int((values.eq(0) & finite).sum())
    return (f'Gust observations: {missing:,} of {len(frame):,} loaded reports have missing/nonfinite gusts; '
            f'these are excluded from pairing. {zeros:,} recorded zeros are retained. '
            'Coverage reflects available gust reports, not all wind reports.')
