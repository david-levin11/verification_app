"""Compare two forecasts on common targets and a single shared observation."""
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from config import (MODELS, PERCENTILES, CATEGORY_CONFIG, get_available_elements,
                    get_available_obs_sources, get_element_config, is_probabilistic,
                    FORECAST_HOURS_BY_MODEL_ELEMENT)
from comparison_loader import load_comparison_data
from wind_verification import (filter_observed_speed, filter_observed_sector,
                               direction_cases, direction_scores)
from wind_comparison_panel import render_direction_comparison
from comparison import (comparison_cases, comparison_scores, grouped_scores,
                        paired_mae_interval, METRIC_LABELS)
from comparison_plots import (plot_group_scores, plot_probability_comparison,
                              station_difference_map)

from page_controls import PageControls
from station_selection import station_ids_input, parse_station_ids, sync_map_selection
from station_metadata import normalize_station_metadata, network_elevation_controls, station_context_table

ui = PageControls('compare')
sync_map_selection('compare', 'compare_stations')

st.title('Model Comparison')
st.caption('Both forecasts are scored against the same observation on matched targets.')
models=[m for m in MODELS if m!='urma']
archive_root=ui.sidebar.text_input('Local Archive Root',st.session_state.get('archive_root','../model'),key='compare_archive_root')
a_col,b_col=ui.columns(2)
model_a=a_col.selectbox('Model A (reference)',models,index=models.index('ndfd'),key='compare_model_a')
model_b=b_col.selectbox('Model B',models,index=models.index('nbm'),key='compare_model_b')
common=[e for e in get_available_elements(model_a) if e in get_available_elements(model_b)]
if not common:
    st.warning('These models have no configured elements in common.');st.stop()
element=ui.sidebar.selectbox('Shared element',common,key='compare_element')
cfg=get_element_config(element)
obs=ui.sidebar.selectbox('Verification Source',get_available_obs_sources(element),key=f'compare_obs_{element}')
prob_a,prob_b=is_probabilistic(model_a,element),is_probabilistic(model_b,element)
percentile_a=(a_col.selectbox('Model A point percentile',PERCENTILES,index=PERCENTILES.index('50'),key=f'compare_pct_a_{element}') if prob_a else None)
percentile_b=(b_col.selectbox('Model B point percentile',PERCENTILES,index=PERCENTILES.index('50'),key=f'compare_pct_b_{element}') if prob_b else None)
label_a=f'A: {model_a.upper()}' + (f' p{percentile_a}' if prob_a else '')
label_b=f'B: {model_b.upper()}' + (f' p{percentile_b}' if prob_b else '')
if model_a==model_b and percentile_a==percentile_b:
    st.info('The models and point forecasts are identical; an offset can still compare different runs.')

d1,d2=ui.sidebar.columns(2)
start=d1.date_input('Start Date',pd.Timestamp('2025-10-01').date(),key='compare_start')
end=d2.date_input('End Date',datetime.now(timezone.utc).date(),key='compare_end')
l1,l2=ui.sidebar.columns(2)
lead_min=l1.number_input('A minimum lead (h)',0,240,0,step=6,key='compare_lead_min')
lead_max=l2.number_input('A maximum lead (h)',0,240,72,step=6,key='compare_lead_max')
threshold=ui.sidebar.selectbox(f'Event threshold ({cfg["units"]})',cfg['thresholds'],
    index=cfg['thresholds'].index(cfg['default_threshold']),key=f'compare_threshold_{element}')
operators=['>=','>','<=','<']
operator=ui.sidebar.selectbox('Event definition',operators,
    index=operators.index(cfg.get('threshold_operator','>=')),key=f'compare_operator_{element}')
obs_minutes=ui.sidebar.number_input('Observation time tolerance (minutes)',0,180,60,step=5,key='compare_obs_tolerance')
ui.sidebar.caption('Accumulation durations must agree; the tolerance applies to window endpoints. Daily temperatures use their configured anchor date.')

st.subheader('Forecast reference matching')
use_offset=ui.checkbox('Offset Model B reference time relative to Model A',key='compare_use_offset')
offset=ui.number_input('Model B offset (hours; negative = earlier)',-72.0,72.0,-6.0,step=1.0,key='compare_offset') if use_offset else 0.
ref_tolerance=ui.number_input('Reference-time tolerance (hours)',0.0,6.0,1.0,step=.5,key='compare_ref_tolerance')
st.caption(f'For each A forecast, select B at A reference {offset:+g} hours, within ±{ref_tolerance:g} hours. Valid targets must match. Actual offsets and both leads appear in the paired data.')

@st.cache_data
def read_metadata(path):
    p=Path(path)
    if not p.is_file():
        return pd.DataFrame()
    data=pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p)
    if 'station_id' not in data and 'stid' in data:
        data=data.rename(columns={'stid':'station_id'})
    if 'station_id' in data:
        data['station_id']=data.station_id.astype(str).str.strip()
    return normalize_station_metadata(data)

metadata_path=ui.sidebar.text_input('Station Metadata Path',st.session_state.get('metadata_path','../metadata/ak_station_metadata.parquet'),key='compare_metadata')
try:
    metadata=read_metadata(metadata_path)
except Exception as exc:
    st.warning(f'Could not read station metadata: {exc}');metadata=pd.DataFrame()
filtered_meta=metadata.copy()
if not metadata.empty:
    with st.expander('Station filters'):
        columns=ui.columns(3)
        for widget_col,field,label in zip(columns,['wfo_best','station_context','public_zone_id'],['WFO','Station context','Public zone']):
            if field in filtered_meta:
                options=['All']+sorted(filtered_meta[field].dropna().astype(str).unique().tolist())
                chosen=widget_col.selectbox(label,options,key=f'compare_filter_{field}')
                if chosen!='All':filtered_meta=filtered_meta[filtered_meta[field].astype(str).eq(chosen)]
        filtered_meta=network_elevation_controls(filtered_meta, ui, 'compare')
        use_filtered=ui.checkbox('Use all stations matching these filters',key='compare_filtered_stations')
        st.caption('Click a column heading to sort the matching station list.')
        st.dataframe(station_context_table(filtered_meta),hide_index=True,use_container_width=True)
else:
    use_filtered=False
station_text=station_ids_input('compare', 'compare_stations', 'Station IDs (comma-separated)')
stations=(filtered_meta.station_id.dropna().unique().tolist() if use_filtered and 'station_id' in filtered_meta else
          parse_station_ids(station_text))
st.caption(f'{len(stations)} stations selected.')
use_dir=ui.checkbox('Filter by observed wind direction',key='compare_use_direction') if cfg.get('supports_direction_filter') else False
if use_dir:
    c1,c2=ui.columns(2)
    dir_min=c1.number_input('Minimum observed direction',0,360,315,key='compare_dir_min')
    dir_max=c2.number_input('Maximum observed direction',0,360,45,key='compare_dir_max')
else:
    dir_min=dir_max=None
speed_minimum = None
verify_direction = False
direction_min_speed = 5.
direction_error_threshold = 45
if element in ['wind', 'gust']:
    st.subheader('Wind verification options' if element == 'wind' else 'Gust verification options')
    filter_speed = ui.checkbox('Set a minimum observed speed for wind-speed verification' if element == 'wind' else 'Set a minimum observed gust', key='compare_filter_speed' if element == 'wind' else 'compare_filter_gust')
    if filter_speed:
        speed_minimum = ui.number_input('Minimum observed speed for speed scores (kt)' if element == 'wind' else 'Minimum observed gust (kt)',
            min_value=0., value=5., step=1., key='compare_speed_minimum' if element == 'wind' else 'compare_gust_minimum')
        st.caption('Applied to all speed/gust scores and plots, including probabilities. False alarms during lighter observed values are excluded; unfiltered scores remain useful.')
    verify_direction = ui.checkbox('Verify wind direction', key='compare_verify_direction') if element == 'wind' else False
    if verify_direction:
        w1, w2 = ui.columns(2)
        direction_min_speed = w1.number_input('Minimum observed speed for direction (kt)',
            min_value=0., value=5., step=1., key='compare_direction_min_speed')
        direction_error_threshold = w2.number_input('Direction error threshold (degrees)',
            min_value=0, max_value=180, value=45, step=5, key='compare_direction_threshold')
        st.caption('Compare mean/median angular error and the percentage exceeding your threshold. Direction requires archived forecast directions from both models; wind-speed percentiles alone are insufficient.')

context=dict(model_a=model_a,model_b=model_b,element=element,obs=obs,percentile_a=percentile_a,
    percentile_b=percentile_b,start=start,end=end,lead_min=lead_min,lead_max=lead_max,
    threshold=threshold,operator=operator,obs_minutes=obs_minutes,offset=offset,
    ref_tolerance=ref_tolerance,stations=stations,
    archive_root=archive_root,use_dir=use_dir,dir_min=dir_min,dir_max=dir_max,
    speed_minimum=speed_minimum,verify_direction=verify_direction,
    direction_min_speed=direction_min_speed,direction_error_threshold=direction_error_threshold)

if st.button('Run Model Comparison',type='primary',key='compare_run'):
    try:
        if lead_min>lead_max:raise ValueError('Minimum lead must not exceed maximum lead')
        if not stations:raise ValueError('Select at least one station')
        horizon=max([lead_max]+FORECAST_HOURS_BY_MODEL_ELEMENT.get(model_a,{}).get(element,[])+
                    FORECAST_HOURS_BY_MODEL_ELEMENT.get(model_b,{}).get(element,[]))+abs(offset)+ref_tolerance+48
        with st.spinner('Loading forecasts and matching common verification cases...'):
            a,b,o,warnings=load_comparison_data(archive_root,model_a,model_b,obs,element,start,end,stations,
                horizon,f'{obs_minutes}min')
            pairs,diagnostics=comparison_cases(a,b,o,model_a,model_b,element,percentile_a,percentile_b,
                obs_source=obs,obs_time_tolerance=f'{obs_minutes}min',offset_hours=offset,
                reference_tolerance=f'{ref_tolerance}h',lead_min=lead_min,lead_max=lead_max,
                matching='reference')
            if use_dir:
                pairs = filter_observed_sector(pairs, dir_min, dir_max)
            base_cases = pairs.reset_index(drop=True)
            diagnostics['cases_after_direction_filter'] = len(base_cases)
            direction_result = None
            if verify_direction:
                direction_data, direction_diagnostics = direction_cases(base_cases, direction_min_speed)
                direction_result = dict(cases=direction_data, diagnostics=direction_diagnostics,
                    scores=direction_scores(direction_data, direction_error_threshold))
            pairs = filter_observed_speed(base_cases, speed_minimum).reset_index(drop=True)
            diagnostics['cases_before_speed_filter'] = len(base_cases)
            diagnostics['cases_after_speed_filter'] = len(pairs)
            diagnostics['cases_excluded_by_speed_minimum'] = len(base_cases) - len(pairs)
            scores,sa,sb=comparison_scores(pairs,element,threshold,operator,prob_a,prob_b)
            st.session_state['comparison_result']=dict(cases=pairs,scores=scores,summary_a=sa,summary_b=sb,
                diagnostics=diagnostics,warnings=warnings,context=context.copy(),metadata=metadata.copy(),
                direction_result=direction_result)
    except Exception as exc:
        st.error(f'Comparison could not run: {exc}')

if 'comparison_result' not in st.session_state:
    st.info('Choose two models and run a comparison.');st.stop()
result=st.session_state['comparison_result'];saved=result['context'];pairs=result['cases']
if saved!=context:
    st.info('These results use the previous settings. Run Model Comparison to refresh.')
element=saved['element'];cfg=get_element_config(element)
model_a,model_b=saved['model_a'],saved['model_b']
prob_a,prob_b=is_probabilistic(model_a,element),is_probabilistic(model_b,element)
label_a='A: '+model_a.upper()+(f' p{saved["percentile_a"]}' if prob_a else '')
label_b='B: '+model_b.upper()+(f' p{saved["percentile_b"]}' if prob_b else '')
for message in result['warnings']:st.warning(message)
diag=result['diagnostics']
st.subheader(f'{label_a} versus {label_b}: {cfg["label"]}')
st.caption(f'B offset {saved["offset"]:+g} h; observation tolerance {saved["obs_minutes"]} min; reference tolerance ±{saved["ref_tolerance"]:g} h.')
c1,c2,c3,c4=ui.columns(4)
c1.metric('Shared cases',f'{len(pairs):,}')
c2.metric('A forecasts without B match',f'{diag.get("a_unmatched",0):,}')
c3.metric('Matched forecasts without obs',f'{diag.get("missing_observations",0):,}')
c4.metric('Observed events',f'{result["summary_a"].get("hits",0)+result["summary_a"].get("misses",0):,}')
if saved.get('speed_minimum') is not None:
    st.caption(f"{cfg['label']} scores use observed value ≥ {saved['speed_minimum']:g} kt: {diag['cases_excluded_by_speed_minimum']:,} of {diag['cases_before_speed_filter']:,} cases excluded. The same retained cases are used for both models and all speed/probability plots.")
render_direction_comparison(result, ui, label_a, label_b)
if pairs.empty:
    if diag.get('cases_before_speed_filter', 0) and saved.get('speed_minimum') is not None:
        st.warning('No cases remain for wind-speed scores at this minimum observed speed. Lower the speed-score minimum to include more cases.' if element == 'wind' else 'No cases remain at this minimum observed gust. Lower the gust minimum to include more cases.')
        st.json(diag); st.stop()
    st.warning('No shared verification cases. Check reference offsets/tolerance, lead ranges, archive coverage, and observation windows.')
    st.json(diag);st.stop()
if saved.get('verify_direction'):
    st.subheader('Wind-speed comparison')
st.caption(f'Event: {element} {saved["operator"]} {saved["threshold"]} {cfg["units"]}. Lead filtering/grouping uses Model A; Model B leads are shown separately. Results pool the shared cases. "Better" indicates the smaller error or higher score, not statistical significance.')
metrics=result['scores'].copy()
metrics['better']=metrics.better.replace({'A':label_a,'B':label_b})
st.dataframe(metrics[['label','a','b','difference','better']].rename(
    columns={'label':'Metric','a':label_a,'b':label_b,'difference':'A − B','better':'Better'}),hide_index=True,use_container_width=True)
if ui.checkbox('Estimate confidence for the MAE difference',key='compare_bootstrap'):
    interval=paired_mae_interval(pairs)
    if interval is None:
        st.info('At least five target days are needed for a day-block confidence interval.')
    else:
        st.write(f'95% paired day-block bootstrap interval for MAE(A) − MAE(B): {interval[0]:.3f} to {interval[1]:.3f} {cfg["units"]}.')
        st.caption('All stations and runs within each target day are resampled together; dependence across days can still affect this estimate.')

plot_metrics=metrics.metric.tolist()
metric=ui.selectbox('Metric for charts and station differences',plot_metrics,index=plot_metrics.index('mae'),
                    format_func=lambda m:METRIC_LABELS[m],key=f'compare_display_metric_{element}_{prob_a}_{prob_b}')
lead_tab,map_tab,condition_tab,prob_tab,data_tab=st.tabs(['Lead times','Station differences','Conditions','Probabilities','Paired data & coverage'])
with lead_tab:
    table=grouped_scores(pairs,'lead_day',element,saved['threshold'],saved['operator'],prob_a,prob_b)
    fig=plot_group_scores(table,'lead_day',metric,label_a,label_b,'Model A forecast day')
    st.pyplot(fig);plt.close(fig)
    st.dataframe(table[table.metric.eq(metric)][['lead_day','n','observed_events','n_prob','a','b','difference']],hide_index=True)
    st.caption('Each day uses common cases for the two models. Actual lead times can differ because of the selected offset.')
with map_tab:
    station_table=grouped_scores(pairs,'station_id',element,saved['threshold'],saved['operator'],prob_a,prob_b)
    minimum=ui.number_input('Minimum shared cases per station',1,10000,10,key='compare_min_cases')
    deck,map_data=station_difference_map(station_table,result['metadata'],metric,label_a,label_b,minimum)
    if deck is None:st.info('A station map needs matching metadata with latitude/longitude and enough shared cases.')
    else:
        st.caption(f'Blue: {label_a} better. Orange: {label_b} better. White: similar. Bias compares distance from zero; frequency bias compares distance from one.')
        st.caption('Circle size reflects shared case counts. Marker sizes stay readable as you zoom.')
        st.pydeck_chart(deck,use_container_width=True)
    display_table=station_table[station_table.metric.eq(metric)]
    context=station_context_table(result['metadata'])
    if 'station_id' in context:
        display_table=display_table.merge(context.drop_duplicates('station_id'),on='station_id',how='left')
    st.dataframe(display_table,hide_index=True,use_container_width=True)
with condition_tab:
    condition=ui.radio('Break down by',['Observed category','Month'],horizontal=True,key='compare_condition')
    work=pairs.copy()
    if condition=='Month':
        work['condition']=work.target_time.dt.strftime('%Y-%m')
    else:
        sets=cfg.get('category_sets',[])
        if sets:
            category=ui.selectbox('Category set',sets,key=f'compare_category_{element}')
            specification=CATEGORY_CONFIG[category]
            work['condition']=pd.cut(work.obs_value,bins=specification['bins'],
                labels=list(specification['labels'].values()))
        else:
            work['condition']=np.where(work.obs_value>=saved['threshold'],'At/above threshold','Below threshold')
    table=grouped_scores(work.dropna(subset=['condition']),'condition',element,saved['threshold'],saved['operator'],prob_a,prob_b)
    if condition=='Observed category' and metric in ['pod','far','csi','frequency_bias']:
        st.info(f"Categories group cases by the observed value; the event remains {cfg['label']} "
                f"{saved['operator']} {saved['threshold']:g} {cfg['units']}. These scores measure "
                "that event within each category, rather than whether the forecast chose the same category. "
                "POD = hits / observed events. A category with cases but zero observed events has undefined POD (N/A).")
    fig=plot_group_scores(table,'condition',metric,label_a,label_b,condition)
    st.pyplot(fig);plt.close(fig)
    st.dataframe(table[table.metric.eq(metric)],hide_index=True,use_container_width=True)
    if metric=='pod':
        st.caption('n counts all shared cases in the group; observed_events counts observations meeting the selected event threshold. More non-event cases do not make POD defined.')
    st.caption('Condition scores are descriptive. Overall threshold scores include all common cases, including non-events and false alarms.')
with prob_tab:
    if prob_a or prob_b:
        if not(prob_a and prob_b):
            st.info('Only one model provides a probability distribution. The point forecasts are compared above; probability diagnostics below describe that model alone.')
        ptable=[]
        for label,summary,prob in [('A: '+model_a.upper(),result['summary_a'],prob_a),('B: '+model_b.upper(),result['summary_b'],prob_b)]:
            if prob:ptable.append({'Model':label,'Probability cases':summary.get('n_prob',0),
                'Brier score':summary.get('brier_score',np.nan),'Reliability error':summary.get('reliability_error',np.nan)})
        st.dataframe(pd.DataFrame(ptable),hide_index=True)
        fig=plot_probability_comparison(pairs,element,saved['threshold'],saved['operator'],'A: '+model_a.upper(),'B: '+model_b.upper(),prob_a,prob_b)
        st.pyplot(fig);plt.close(fig)
        st.caption('Both probabilistic models use the intersection of valid probability cases. Quantile interpolation, tied-value handling, and tail approximations are shared with the other verification pages. Reliability error uses 10% probability bins.')
    else:st.info('Neither selected model/element provides archived probability distributions.')
with data_tab:
    st.json(diag)
    columns=['station_id','target_time','a_valid_time','b_valid_time','a_init_time','b_init_time','a_forecast_hour','b_forecast_hour',
        'actual_offset_hours','reference_error_hours','a_model_value','b_model_value','obs_value',
        'a_forecast_direction','b_forecast_direction','observed_direction',
        'obs_valid_time','obs_time_offset_minutes','obs_window_start','obs_window_end']
    st.dataframe(pairs[[c for c in columns if c in pairs]].head(1000),hide_index=True,use_container_width=True)
    st.download_button('Download all paired cases (CSV)',pairs.to_csv(index=False),
                       file_name='model_comparison_cases.csv',mime='text/csv',key='compare_download')
    st.download_button('Download scorecard (CSV)',result['scores'].to_csv(index=False),
                       file_name='model_comparison_scores.csv',mime='text/csv',key='compare_scores_download')
    if 'obs_time_offset_minutes' in pairs:
        offsets=pairs.obs_time_offset_minutes.abs()
        st.write(f'Observation timing: median absolute offset {offsets.median():.1f} minutes; maximum {offsets.max():.1f} minutes.')
    st.write('Actual A reference hours (UTC):',sorted(pairs.a_init_time.dt.hour.unique().tolist()))
    st.write('Actual B reference hours (UTC):',sorted(pairs.b_init_time.dt.hour.unique().tolist()))
