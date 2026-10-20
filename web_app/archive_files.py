"""Shared monthly archive discovery, including combined wind/gust archives."""
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from config import get_element_config, get_percentile_columns, is_probabilistic


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
