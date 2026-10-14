"""Match forecast references first, then attach one shared observation per case."""
import numpy as np
import pandas as pd
from config import (get_element_config, get_model_pair_date_column,
                    get_pairing_method, get_percentile_columns, is_probabilistic)
from pairing import build_verification_pairs, get_model_value_column
from metrics import compute_summary_metrics
from probability import forecast_probabilities, probability_scores

POINT_METRICS = ['bias', 'mae', 'rmse', 'pod', 'far', 'csi', 'frequency_bias']
PROB_METRICS = ['brier_score', 'reliability_error']
LOWER_BETTER = {'mae', 'rmse', 'brier_score', 'reliability_error'}
HIGHER_BETTER = {'pod', 'csi'}
METRIC_LABELS = {'bias':'Bias', 'mae':'MAE', 'rmse':'RMSE', 'pod':'POD',
    'far':'FAR', 'csi':'CSI', 'frequency_bias':'Frequency bias',
    'brier_score':'Brier score', 'reliability_error':'Reliability error'}


def utc_naive(values):
    return pd.to_datetime(values, utc=True, errors='coerce').dt.tz_convert(None).astype('datetime64[ns]')


def prepare_forecasts(frame, model, element, percentile=None):
    result = frame.copy()
    if 'station_id' not in result and 'stid' in result:
        result = result.rename(columns={'stid':'station_id'})
    if result.empty:
        return pd.DataFrame()
    if 'station_id' not in result or 'valid_time' not in result:
        raise ValueError(f'{model.upper()} lacks station_id or valid_time')
    result = result.dropna(subset=['station_id']).copy()
    result['station_id'] = result.station_id.astype(str).str.strip()
    result['valid_time'] = utc_naive(result.valid_time)
    if 'init_time' not in result or model == 'ndfd':
        if 'forecast_hour' not in result:
            raise ValueError(f'{model.upper()} needs forecast_hour to reconstruct its reference time')
        result['init_time'] = result.valid_time - pd.to_timedelta(
            pd.to_numeric(result.forecast_hour, errors='coerce'), unit='h')
    else:
        result['init_time'] = utc_naive(result.init_time)
    result['forecast_hour'] = (result.valid_time - result.init_time).dt.total_seconds() / 3600
    if is_probabilistic(model, element):
        percentile = str(percentile or '50')
        column = get_percentile_columns(element).get(percentile)
        if column not in result:
            raise ValueError(f'{model.upper()} lacks the requested p{percentile} column ({column})')
    else:
        column = get_model_value_column(result, model, element)
    result['model_value'] = pd.to_numeric(result[column], errors='coerce')
    date_col = get_model_pair_date_column(element)
    result['target_time'] = (utc_naive(result[date_col]).dt.normalize()
        if get_pairing_method(element) == 'date' else result.valid_time)
    result = result.dropna(subset=['init_time','valid_time','target_time','model_value'])
    result = result[np.isfinite(result.model_value) & result.forecast_hour.ge(0)]
    return result


def lead_group(hours):
    # Day 1 = 0..24 h; Day 2 = >24..48 h, etc.
    return np.maximum(1, np.ceil(hours / 24)).astype(int)


def match_forecasts(model_a_frame, model_b_frame, model_a, model_b, element,
                    percentile_a=None, percentile_b=None, offset_hours=0,
                    reference_tolerance='0h', lead_min=0, lead_max=168,
                    matching='reference', cutoff=None):
    """B reference target = A reference + signed offset (negative is earlier).

    In reference mode every distinct A reference/target is a case. In cutoff
    mode choose one latest A reference per station/target at or before cutoff,
    and one latest B at/before cutoff+offset. No publication times are assumed.
    """
    a = prepare_forecasts(model_a_frame, model_a, element, percentile_a)
    b = prepare_forecasts(model_b_frame, model_b, element, percentile_b)
    diagnostics = {'a_loaded':len(model_a_frame), 'b_loaded':len(model_b_frame),
                   'a_invalid':len(model_a_frame)-len(a), 'b_invalid':len(model_b_frame)-len(b)}
    if a.empty or b.empty:
        diagnostics.update(a_eligible=len(a), forecast_matches=0, a_unmatched=len(a))
        return pd.DataFrame(), diagnostics
    # Deterministic order for duplicate keys within input; last archived row wins.
    keys = ['station_id','target_time','init_time']
    diagnostics['a_duplicate_rows'] = int(a.duplicated(keys).sum())
    diagnostics['b_duplicate_rows'] = int(b.duplicated(keys).sum())
    a = a.drop_duplicates(keys, keep='last')
    b = b.drop_duplicates(keys, keep='last')
    if matching == 'cutoff':
        if cutoff is None:
            raise ValueError('A common reference cutoff is required')
        cutoff = pd.Timestamp(cutoff)
        if cutoff.tzinfo is not None:
            cutoff = cutoff.tz_convert('UTC').tz_localize(None)
        a = a[a.init_time.le(cutoff)].sort_values('init_time', kind='stable').drop_duplicates(
            ['station_id','target_time'], keep='last')
        b = b[b.init_time.le(cutoff + pd.Timedelta(hours=offset_hours))].sort_values(
            'init_time', kind='stable').drop_duplicates(['station_id','target_time'], keep='last')
    elif matching != 'reference':
        raise ValueError('Unknown reference matching mode')
    # The lead range belongs to A. B leads deliberately differ with an offset.
    a = a[a.forecast_hour.between(lead_min, lead_max)].copy()
    diagnostics['a_eligible'] = len(a)
    a['_case_id'] = np.arange(len(a))
    a = a.rename(columns={c:'a_'+c for c in a if c not in ['station_id','target_time','_case_id']})
    b = b.rename(columns={c:'b_'+c for c in b if c not in ['station_id','target_time']})
    if a.empty or b.empty:
        diagnostics.update(forecast_matches=0, a_unmatched=len(a))
        return pd.DataFrame(), diagnostics
    if matching == 'cutoff':
        merged = a.merge(b, on=['station_id','target_time'], how='left', validate='one_to_one')
    else:
        tolerance = pd.Timedelta(reference_tolerance)
        if tolerance < pd.Timedelta(0):
            raise ValueError('Reference tolerance must be non-negative')
        a['_desired_b_reference'] = a.a_init_time + pd.Timedelta(hours=offset_hours)
        merged = pd.merge_asof(a.sort_values('_desired_b_reference'), b.sort_values('b_init_time'),
            left_on='_desired_b_reference', right_on='b_init_time',
            by=['station_id','target_time'], direction='nearest', tolerance=tolerance)
    merged = merged.dropna(subset=['b_init_time','b_model_value']).copy()
    diagnostics.update(forecast_matches=len(merged), a_unmatched=len(a)-len(merged))
    if not merged.empty:
        merged['actual_offset_hours'] = (merged.b_init_time - merged.a_init_time).dt.total_seconds()/3600
        merged['requested_offset_hours'] = offset_hours
        merged['reference_error_hours'] = (merged.actual_offset_hours - offset_hours
                                           if matching == 'reference' else np.nan)
        merged['lead_day'] = lead_group(merged.a_forecast_hour)
    return merged, diagnostics


def attach_shared_observations(matched, observations, model_a, element,
                               percentile_a=None, obs_source='obs', obs_time_tolerance='1h'):
    if matched.empty:
        return matched
    # Pair once using the A target. Both forecasts receive this identical observation.
    columns = {c:c[2:] for c in matched if c.startswith('a_')}
    anchor = matched[list(columns)].rename(columns=columns)
    anchor['station_id'] = matched.station_id
    paired = build_verification_pairs(anchor, observations, model_a, obs_source, element,
                                     percentile_a, obs_time_tolerance)
    if paired.empty:
        return pd.DataFrame()
    obs_cols = ['station_id','init_time','valid_time','obs_value','obs_valid_time',
                'obs_time_offset_minutes','obs_window_start','obs_window_end','pair_date']
    # Date extrema retain their existing configured anchor-date convention.
    for col in get_element_config(element).get('direction_candidates', []):
        observed_col = col + '_obs' if col + '_obs' in paired else col
        if col in observations and observed_col in paired:
            paired['observed_direction'] = paired[observed_col]
            obs_cols.append('observed_direction')
            break
    obs_cols = list(dict.fromkeys(c for c in obs_cols if c in paired))
    paired = paired[obs_cols].drop_duplicates(['station_id','init_time','valid_time'],keep='last')
    paired = paired.rename(columns={'init_time':'a_init_time','valid_time':'a_valid_time'})
    result = matched.merge(paired, on=['station_id','a_init_time','a_valid_time'],
                           how='inner', validate='many_to_one')
    result = result[np.isfinite(pd.to_numeric(result.obs_value, errors='coerce'))].copy()
    return result


def comparison_cases(a, b, observations, model_a, model_b, element,
                     percentile_a=None, percentile_b=None, obs_source='obs',
                     obs_time_tolerance='1h', **matching_options):
    matched, diagnostics = match_forecasts(a,b,model_a,model_b,element,
        percentile_a,percentile_b,**matching_options)
    pairs = attach_shared_observations(matched,observations,model_a,element,
                                      percentile_a,obs_source,obs_time_tolerance)
    diagnostics.update(observation_rows=len(observations), matched_cases=len(pairs),
                       missing_observations=len(matched)-len(pairs))
    return pairs, diagnostics


def model_view(cases, side):
    result = cases[[c for c in cases if c.startswith(side+'_')]].copy()
    result = result.rename(columns={c:c[2:] for c in result})
    result['station_id'] = cases.station_id
    result['obs_value'] = cases.obs_value
    return result


def metric_preference(metric, a, b):
    if not np.isfinite(a) or not np.isfinite(b):
        return 'Unavailable'
    if metric == 'bias':
        a,b = abs(a),abs(b)
    elif metric == 'frequency_bias':
        a,b = abs(a-1),abs(b-1)
    elif metric in HIGHER_BETTER:
        a,b = -a,-b
    if np.isclose(a,b,rtol=1e-8,atol=1e-10):
        return 'Tie'
    return 'A' if a < b else 'B'


def summary_for(view, threshold, operator):
    summary = compute_summary_metrics(view, threshold, threshold_operator=operator)
    events = summary.get('hits',0)+summary.get('misses',0)
    summary['frequency_bias'] = ((summary.get('hits',0)+summary.get('false_alarms',0))/events
                                 if events else np.nan)
    return summary


def comparison_scores(cases, element, threshold, operator='>=', probability_a=False, probability_b=False):
    if cases.empty:
        return pd.DataFrame(), {}, {}
    av,bv = model_view(cases,'a'),model_view(cases,'b')
    sa,sb = summary_for(av,threshold,operator),summary_for(bv,threshold,operator)
    if probability_a or probability_b:
        pa = forecast_probabilities(av,element,threshold,operator) if probability_a else None
        pb = forecast_probabilities(bv,element,threshold,operator) if probability_b else None
        valid = pa.notna() & pb.notna() if probability_a and probability_b else (pa if probability_a else pb).notna()
        if probability_a:
            sa.update(probability_scores(av.loc[valid],element,threshold,operator))
        if probability_b:
            sb.update(probability_scores(bv.loc[valid],element,threshold,operator))
    rows=[]
    for metric in POINT_METRICS + (PROB_METRICS if probability_a and probability_b else []):
        va,vb = sa.get(metric,np.nan),sb.get(metric,np.nan)
        rows.append(dict(metric=metric,label=METRIC_LABELS[metric],a=va,b=vb,
                         difference=va-vb,better=metric_preference(metric,va,vb)))
    return pd.DataFrame(rows),sa,sb


def grouped_scores(cases, group, element, threshold, operator='>=', probability_a=False, probability_b=False):
    tables=[]
    for name,part in cases.groupby(group,dropna=False,sort=True,observed=True):
        table,sa,sb=comparison_scores(part,element,threshold,operator,probability_a,probability_b)
        table[group]=name;table['n']=len(part);table['observed_events']=sa.get('hits',0)+sa.get('misses',0)
        probability_counts=[s.get('n_prob',0) for s,p in [(sa,probability_a),(sb,probability_b)] if p]
        table['n_prob']=min(probability_counts) if probability_counts else 0
        tables.append(table)
    return pd.concat(tables,ignore_index=True) if tables else pd.DataFrame(
        columns=['metric','label','a','b','difference','better',group,'n','observed_events','n_prob'])


def paired_mae_interval(cases, repetitions=400, seed=42):
    """Paired day-block bootstrap; all stations and runs on a target day stay together."""
    difference=(cases.a_model_value-cases.obs_value).abs()-(cases.b_model_value-cases.obs_value).abs()
    blocks=pd.DataFrame({'day':cases.target_time.dt.normalize(),'difference':difference}).groupby('day').difference.agg(['sum','count'])
    if len(blocks)<5:
        return None
    generator=np.random.default_rng(seed)
    indices=generator.integers(0,len(blocks),size=(repetitions,len(blocks)))
    samples=blocks['sum'].to_numpy()[indices].sum(axis=1)/blocks['count'].to_numpy()[indices].sum(axis=1)
    return tuple(np.quantile(samples,[.025,.975]))
