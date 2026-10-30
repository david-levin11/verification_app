"""Read-only adapters for deterministic RRFS and derived REFS archives."""
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
from config import get_percentile_columns

REFS_VARIABLES = {'wind':'wind_speed_kt', 'gust':'wind_gust_kt', 'rh':'rh', 'precip6hr':'precip_6h'}
ENSEMBLE_COLUMNS = ['_forecast_model','ensemble_init_time','ensemble_forecast_hour',
    'value_column','n_expected','n_available','complete','ensemble_eligible',
    'statistics_config','probability_operator','require_complete','quantile_method',
    'weighting','mean','spread']


def refs_archive_root(root, refs_root=None):
    return Path(refs_root).expanduser() if refs_root else Path(root).expanduser().parent/'derived'/'refs'


def refs_root_control(ui, root, enabled):
    if not enabled:return None
    value=ui.text_input('REFS Derived Archive Root',str(refs_archive_root(root)),key='refs_root')
    ui.caption('REFS reads derived statistics here. Wind and gust share wind files. Completeness uses available/expected members at each lead, not a fixed ensemble size.')
    return value


def register_forecast_archive(connection, files, model, element):
    """Normalize before applying date/lead filters, preserving cumulative endpoints."""
    interval_model=model in ['rrfs','hrrr'] and element=='precip6hr'
    connection.from_parquet(files, union_by_name=True,filename=interval_model).create_view('raw_forecast_archive', replace=True)
    columns=connection.table('raw_forecast_archive').columns
    source='SELECT * FROM raw_forecast_archive'
    if model=='refs':
        required=['ensemble_init_time','ensemble_forecast_hour','value_column','n_expected','n_available','complete']
        missing=[c for c in required if c not in columns]
        if missing:raise ValueError(f'REFS archive lacks {", ".join(missing)}')
        variable=REFS_VARIABLES[element]
        eligible='(COALESCE(complete, false) AND n_expected > 0 AND n_available = n_expected)'
        excluded=[c for c in ['init_time','forecast_hour'] if c in columns]
        star='*'+(' EXCLUDE ('+', '.join(excluded)+')' if excluded else '')
        extra=[f'ensemble_init_time AS init_time', 'ensemble_forecast_hour AS forecast_hour',
               "'refs' AS _forecast_model", f'{eligible} AS ensemble_eligible']
        # Mask every statistic on incomplete rows, retaining counts for diagnostics.
        statistics=[c for c in columns if c in ['mean','spread'] or c.startswith('prob_')]
        if statistics:
            star+=' REPLACE ('+', '.join(f'CASE WHEN {eligible} THEN "{c}" ELSE NULL END AS "{c}"' for c in statistics)+')'
        for level, canonical in get_percentile_columns(element).items():
            value=f'"p{level}"' if f'p{level}' in columns else 'NULL'
            extra.append(f'CASE WHEN {eligible} THEN {value} ELSE NULL END AS "{canonical}"')
        source=f"SELECT {star}, {', '.join(extra)} FROM raw_forecast_archive WHERE value_column = '{variable}'"
    elif interval_model:
        # Inspect per-file schemas: a union's NULL column cannot tell an old file
        # from a genuinely missing interval in a newer file.
        choices=[]
        cumulative=False
        for path in files:
            schema=pq.read_schema(path).names
            interval=next((c for c in ['precip_6h','precip_accum_6hr','precip6hr'] if c in schema),None)
            if interval is None and 'precip_accum' not in schema:
                raise ValueError(f'{model.upper()} lacks a six-hour precipitation field or cumulative endpoints in {path}')
            cumulative |= interval is None
            literal="'"+str(path).replace("'","''")+"'"
            value=f'current."{interval}"' if interval else """CASE
                WHEN current.valid_time-current.init_time = INTERVAL '6 hours' THEN current.precip_accum
                WHEN current.valid_time-current.init_time > INTERVAL '6 hours'
                     AND previous.precip_accum IS NOT NULL AND current.precip_accum IS NOT NULL
                THEN greatest(current.precip_accum-previous.precip_accum,0)
                ELSE NULL END"""
            choices.append(f'WHEN current.filename = {literal} THEN {value}')
        value='CASE '+ ' '.join(choices)+' ELSE NULL END'
        if cumulative:
            # Keep the last occurrence before joining exact 6 h endpoints.
            source=f"""WITH numbered AS (SELECT *, row_number() OVER () AS _archive_order FROM raw_forecast_archive),
                totals AS (SELECT * EXCLUDE (_archive_order) FROM numbered QUALIFY
                    row_number() OVER (PARTITION BY station_id,init_time,valid_time ORDER BY _archive_order DESC)=1)
                SELECT current.*, {value} AS verification_precip_6h
                FROM totals current LEFT JOIN totals previous
                ON current.station_id=previous.station_id AND current.init_time=previous.init_time
                AND previous.valid_time=current.valid_time-INTERVAL '6 hours' """
        else:
            source=f'SELECT current.*, {value} AS verification_precip_6h FROM raw_forecast_archive current'
    connection.sql(source).create_view('forecast_archive',replace=True)


def archive_diagnostics(frame, model):
    if model!='refs' or frame.empty:return []
    excluded=int((~frame.ensemble_eligible.fillna(False)).sum())
    messages=[f'REFS: {excluded:,} of {len(frame):,} loaded rows excluded for incomplete/invalid ensembles. '
              'Completeness uses each row’s n_available/n_expected; scheduled member departures are allowed.']
    recipes=frame.statistics_config.dropna().unique() if 'statistics_config' in frame else []
    if len(recipes)>1:messages.append('REFS: multiple statistics recipes in the selected period; retain recipe/member counts when interpreting scores.')
    return messages


def probability_description(include_refs=True):
    if not include_refs:
        return ('Probabilities use shared quantile interpolation, tied-value handling and tail assumptions. '
                'All-equal quantiles are approximated as a point mass.')
    return ('REFS uses archived member probabilities when the threshold and strict operator match; '
            'other events use quantile interpolation with tied-value and tail assumptions. '
            'Missing configured member probabilities remain missing. REFS completeness is relative to each lead’s expected members.')
