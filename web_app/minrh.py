"""Daily MinRH validity rules shared by loaders, pairing and comparisons."""
import numpy as np
import pandas as pd


def prepare_minrh(frame,model=None):
    """Require comparable 12 h windows, valid percentages and adequate obs coverage.

    NBM's scalar QMD field is validated as a 12 h minimum by the archiver;
    only its absent interval bounds may be reconstructed. NDFD and observations
    require explicit archived bounds. Never expand a clipped native NDFD period.
    """
    result=frame.copy()
    if result.empty:return result,[]
    observation=model is None
    if 'valid_time' not in result and 'window_end' in result:result['valid_time']=result.window_end
    if 'valid_time' not in result:raise ValueError('MinRH requires a valid_time or window_end')
    result['valid_time']=pd.to_datetime(result.valid_time,utc=True,errors='coerce').dt.tz_convert(None)
    bounds={'window_start','window_end'}
    if not bounds.issubset(result):
        if model=='nbm' and not bounds.intersection(result):
            result['window_end']=result.valid_time
            result['window_start']=result.valid_time-pd.Timedelta(hours=12)
        else:raise ValueError('MinRH requires explicit window_start and window_end columns')
    for col in bounds:result[col]=pd.to_datetime(result[col],utc=True,errors='coerce').dt.tz_convert(None)
    valid=(result.window_end-result.window_start).eq(pd.Timedelta(hours=12)) & result.valid_time.eq(result.window_end)
    # Both currently supported products target the daily 06Z endpoint.
    valid &= result.window_end.eq(result.window_end.dt.normalize()+pd.Timedelta(hours=6))
    if 'window_duration_mismatch' in result:valid &= result.window_duration_mismatch.eq(False).fillna(False)
    if 'window_hours' in result:valid &= pd.to_numeric(result.window_hours,errors='coerce').eq(12)
    column='minrh' if 'minrh' in result else 'obs_value' if observation else 'model_value'
    if column not in result:raise ValueError('MinRH archive lacks the minrh percentage field')
    values=pd.to_numeric(result[column].map(lambda value:None if isinstance(value,(bool,np.bool_)) else value),errors='coerce')
    valid &= np.isfinite(values) & values.between(0,100)
    result[column]=values
    if observation:
        if 'coverage_ok' not in result:raise ValueError('MinRH observations require the archived coverage_ok diagnostic')
        valid &= result.coverage_ok.eq(True).fillna(False)
    if 'rh_units' in result:valid &= result.rh_units.eq('%')
    excluded=int((~valid).sum())
    message=([f'MinRH {"OBS" if observation else model.upper()}: excluded {excluded:,} of {len(result):,} rows '
              'with incomplete/ambiguous windows, invalid percentages, or inadequate observation coverage. '
              'Only full 18Z–06Z windows are verified.'] if excluded else [])
    return result.loc[valid].copy(),message
