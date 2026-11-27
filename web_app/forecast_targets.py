"""Shared verification dates for Alaska daily temperature forecast archives.

Corrected NBM MaxT ends at next-day 06Z. Observations label that 12Z–06Z
window by its starting date. Legacy MaxT at 12Z already carries that date.
NDFD's archived daily labels retain their existing calendar-date convention.
No initialization times or lead hours are rewritten here.
"""
import pandas as pd
from config import experimental_temperature, get_model_pair_date_column, get_pairing_method

NBM_MODELS = {'nbm', 'nbm_exp', 'nbmqmd', 'nbmqmd_exp'}


def forecast_target_time(frame, model, element, align_by_date=False):
    column = forecast_target_column(model, element)
    time = pd.to_datetime(frame[column], errors='coerce', utc=True).dt.tz_convert(None).astype('datetime64[ns]')
    if not align_by_date and get_pairing_method(element) != 'date':
        return time
    target = time.dt.normalize()
    if element == 'maxt' and model in NBM_MODELS:
        # Explicit endpoint convention, not an inference about the run cycle.
        endpoint = time.eq(time.dt.normalize() + pd.Timedelta(hours=6))
        target = target.where(~endpoint, target - pd.Timedelta(days=1))
    return target


def forecast_target_sql(model, element, align_by_date=False):
    """DuckDB equivalent, so date filters and Python pairing cannot diverge."""
    if not align_by_date and get_pairing_method(element) != 'date':
        return 'valid_time'
    column = forecast_target_column(model, element)
    day = f"date_trunc('day', {column})"
    if element == 'maxt' and model in NBM_MODELS:
        return (f"CASE WHEN {column} = {day} + INTERVAL '6 hours' "
                f"THEN {day} - INTERVAL '1 day' ELSE {day} END")
    return day


def forecast_target_column(model, element):
    if experimental_temperature(model, element):
        return 'window_start'
    return get_model_pair_date_column(element) if get_pairing_method(element) == 'date' else 'valid_time'
