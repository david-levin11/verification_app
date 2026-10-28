"""Single-run spatial snapshots, uncertainty diagnostics, and station plumes."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from config import (MODELS, PERCENTILES, get_available_elements, get_available_obs_sources,
                    get_element_config, is_probabilistic)
from data_loader import fetch_data
from plots import plot_storm_timeseries
from page_controls import PageControls
from station_metadata import normalize_station_metadata, network_elevation_controls, station_context_table
from station_selection import selected_station_ids
from storm_analysis import build_storm_cases, available_intervals, interval_summary, evolution_summary, STORM_ELEMENTS
from temperature_storm import plot_temperature_periods, temperature_snapshot_label
from accumulation_storm import plot_accumulation_periods
from storm_visuals import (snapshot_map_data, render_storm_map, plot_evolution,
                           map_colorbar, map_description)

ui = PageControls('storm')
# Keep one page scrollbar. In particular, never constrain the tab panel to the
# remaining viewport height: its map/figures can be taller than a laptop screen.
# Use stable test IDs rather than Streamlit's generated CSS class names.
st.markdown('''<style>
section[data-testid="stMain"], main[data-testid="stMain"],
section.main { overflow-y: auto !important; }
[data-testid="stMainBlockContainer"],
[data-testid="stTabs"],
[data-testid="stTabs"] > div,
[data-testid="stTabs"] [role="tabpanel"] {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
}
</style>''', unsafe_allow_html=True)
st.title('Storm Specific Zoom')
st.caption('Explore one model run across stations and forecast projections. All displayed times are UTC.')
archive_root = ui.sidebar.text_input('Local Archive Root', '../model')
model = ui.sidebar.selectbox('Model', MODELS)
available_elements = [e for e in get_available_elements(model) if e in STORM_ELEMENTS]
element = ui.sidebar.selectbox('Element', available_elements)
cfg = get_element_config(element).copy()
daily = element in ['maxt','mint']
if daily:cfg['units']='°F'
obs = ui.sidebar.selectbox('Verification Source', get_available_obs_sources(element))
probabilistic = is_probabilistic(model, element)
percentile = (ui.sidebar.selectbox('Verification Percentile', PERCENTILES,
              index=PERCENTILES.index(cfg['default_percentile']), key=f'storm_percentile_{element}')
              if probabilistic else None)
threshold = ui.sidebar.number_input(f'Event threshold ({cfg["units"]})', value=float(cfg['default_threshold']),
                                    key=f'storm_threshold_{element}')
operators = ['>=','>','<=','<']
operator = ui.sidebar.selectbox('Event direction', operators,
    index=operators.index(cfg.get('threshold_operator','>=')), key=f'storm_operator_{element}')
if daily:
    minutes=0
    st.sidebar.caption('Daily temperature observations match the forecast date. Reporting-time tolerance does not apply; the observed measurement windows appear in the results.')
else:
    minutes = ui.sidebar.number_input('Observation tolerance (minutes)',0,180,60,step=5,key='storm_obs_minutes')
    if cfg.get('accum_hours'):
        st.sidebar.caption('Accumulation durations must agree. Tolerance applies to the window endpoint.')

@st.cache_data
def read_metadata(path):
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame()
    return normalize_station_metadata(pd.read_parquet(p) if p.suffix.lower()=='.parquet' else pd.read_csv(p))

metadata_path = ui.sidebar.text_input('Station Metadata Path',st.session_state.get('metadata_path','../metadata/ak_station_metadata.parquet'),key='storm_metadata')
try:
    metadata = read_metadata(metadata_path)
except Exception as exc:
    st.warning(f'Could not read metadata: {exc}')
    metadata = pd.DataFrame()

init_text = ui.text_input('Model Init Time (YYYY-MM-DD HH:MM:SS)','2026-02-21 00:00:00')
left,right = ui.columns(2)
start = left.date_input('Plot Start Date',pd.Timestamp('2026-02-21'))
end = right.date_input('Plot End Date',pd.Timestamp('2026-02-24'))
scope = ui.radio('Stations to load',['Filtered metadata stations','Map Explorer selections'],
                 key='storm_station_scope',horizontal=True)
filtered = metadata.copy()
if scope=='Filtered metadata stations':
    if metadata.empty:
        st.warning('Provide station metadata to load filtered stations, or choose stations selected in Map Explorer.')
    else:
        with st.expander('Station filters',expanded=True):
            cols=ui.columns(2)
            for widget, field, label in zip(cols,['wfo_best','station_context'],['WFO','Station context']):
                if field in filtered:
                    options=['All']+sorted(filtered[field].dropna().astype(str).unique().tolist())
                    chosen=widget.selectbox(label,options,key=f'storm_filter_{field}')
                    if chosen!='All':filtered=filtered[filtered[field].astype(str).eq(chosen)]
            filtered=network_elevation_controls(filtered,ui,'storm')
            st.dataframe(station_context_table(filtered),hide_index=True,use_container_width=True)
if scope=='Map Explorer selections':
    stations=selected_station_ids()
    if stations:st.caption('Selected in Map Explorer: '+', '.join(stations))
    else:st.info('Select stations on the Map Explorer map; they will appear here automatically.')
else:
    stations=filtered.station_id.dropna().unique().tolist() if 'station_id' in filtered else []
st.caption(f'{len(stations):,} stations requested. Maps require metadata coordinates; station plots and scores do not.')
context=dict(model=model,element=element,obs=obs,percentile=percentile,threshold=threshold,
    operator=operator,minutes=minutes,init=init_text,start=start,end=end,stations=stations,
    archive_root=archive_root,metadata_path=metadata_path)

if st.button('Generate Storm Timeseries',type='primary'):
    try:
        if start>end:raise ValueError('Plot start date must not be after end date.')
        if not stations:raise ValueError('Choose at least one station.')
        init=pd.to_datetime(init_text,utc=True,errors='raise').tz_convert(None)
        if pd.isna(init):raise ValueError('Enter a valid model initialization time.')
        with st.spinner(f'Loading one {model.upper()} run for {len(stations):,} station(s)...'):
            modeldf,obdf,message=fetch_data('Storm Specific Zoom',model,obs,start,end,stations,[],init,
                {},percentile,element=element,archive_root=archive_root,obs_time_tolerance=f'{minutes}min')
            if modeldf.empty:raise ValueError(message or 'No model forecasts found for this run and event period.')
            cases=build_storm_cases(modeldf,obdf,model,obs,element,init,percentile,
                f'{minutes}min',threshold,operator)
            if cases.empty:raise ValueError('No valid forecasts matched the requested initialization.')
            generation=st.session_state.get('_storm_generation',0)+1
            st.session_state['_storm_generation']=generation
            st.session_state['storm_result']=dict(context=context.copy(),cases=cases,
                modeldf=modeldf,obdf=obdf,metadata=metadata.copy(),warnings=[message] if message else [],
                generation=generation,init=init)
    except Exception as exc:
        st.error(f'Storm analysis could not run: {exc}')

result=st.session_state.get('storm_result')
if result is None:
    st.info('Choose a run, event period, and station set, then generate the storm analysis.')
    st.stop()
saved=result['context']
if saved!=context:
    st.info('Controls have changed. Generate again to refresh the results; the displays below still use the saved request.')
cases=result['cases'];cfg=get_element_config(saved['element']).copy()
daily=saved['element'] in ['maxt','mint']
accumulation=cfg.get('accum_hours') is not None
if daily:cfg['units']='°F'
spread_units='percentage points' if saved['element']=='rh' else cfg['units']
probabilistic=is_probabilistic(saved['model'],saved['element'])
for message in result['warnings']:st.warning(message)
matching_label='matched by forecast date' if daily else f'observation tolerance ±{saved["minutes"]} min'
st.caption(f"{saved['model'].upper()} {cfg['label']} — initialized {result['init']} UTC. "
           f"Event: {saved['operator']} {saved['threshold']:g} {cfg['units']}; {matching_label}.")
left,right=ui.columns(2)
valid_times=[pd.Timestamp(t) for t in cases.target_time.drop_duplicates().sort_values()]
valid=left.selectbox('Snapshot forecast date' if daily else 'Snapshot valid time',valid_times,key=f'storm_valid_{result["generation"]}',
    format_func=(lambda t: temperature_snapshot_label(t,cases,saved['element'])) if daily else
    (lambda t: f'{pd.Timestamp(t):%Y-%m-%d %H:%M} UTC (+{(pd.Timestamp(t)-result["init"]).total_seconds()/3600:g} h)'))
snapshot=cases[cases.target_time.eq(valid)].copy()
station_options=sorted(cases.station_id.unique().tolist())
if st.session_state.get('storm_detail_station') not in station_options:
    st.session_state.pop('storm_detail_station',None)

spatial,evolution,detail=st.tabs(['Spatial snapshot','Storm evolution','Station detail'])
with spatial:
    st.write(f'{len(snapshot):,} forecast stations; {snapshot.obs_value.notna().sum():,} matched observations; '
             f'{snapshot.obs_value.isna().sum():,} without a matched observation '+
             ('for this forecast date.' if daily else 'at this projection.'))
    map_options={'Forecast':'model_value','Observation':'obs_value','Signed error':'error','Absolute error':'absolute_error'}
    if probabilistic:
        map_options={'Observed percentile':'observed_percentile','Median forecast error':'median_error',
            'Threshold probability':'forecast_probability',**map_options}
        for lo,hi in available_intervals(cases):map_options[f'Spread p{lo}–p{hi}']=f'width_{lo}_{hi}'
    if 'angular_error' in cases and saved['element']=='wind':
        map_options['Direction angular error']='angular_error'
    map_label=ui.selectbox('Map display',list(map_options),key=f'storm_map_display_{saved["element"]}_{probabilistic}')
    metric=map_options[map_label]
    st.write(map_description(metric,map_label,cfg,saved['percentile'],saved['threshold'],saved['operator']))
    map_snapshot=snapshot.copy()
    if metric=='angular_error':
        minimum=ui.number_input('Minimum observed speed for direction (kt)',min_value=0.,value=5.,step=1.,key='storm_direction_minimum')
        map_snapshot.loc[map_snapshot.obs_value.lt(minimum),'angular_error']=np.nan
        st.caption('Direction errors use archived directions and exclude calm/nonpositive forecast or observed speeds.')
    map_data,view,limits=snapshot_map_data(map_snapshot,result['metadata'],metric)
    if map_data.empty:
        st.info('No stations have both coordinates and a valid value for this map display. The tables and station plots remain available.')
    else:
        unit = ('percentile' if metric=='observed_percentile' else 'probability (0–1)' if metric=='forecast_probability'
                else 'degrees' if metric=='angular_error' else spread_units
                if metric in ['error','absolute_error','median_error'] or metric.startswith('width_') else cfg['units'])
        st.caption(f'{len(map_data)} stations plotted. Click a station to populate Station detail.')
        render_storm_map(map_data,metric,view,result['generation'])
        fig=map_colorbar(metric,limits,map_label,unit)
        st.pyplot(fig);plt.close(fig)
        if metric=='forecast_probability':
            st.caption('Outline: green = event observed; purple = event not observed; gray = no matched observation. Gold marks the selected station.')
            st.caption('Probabilities are approximated from archived quantiles using the same interpolation and tail assumptions as the other verification pages.')
    if probabilistic:
        st.subheader('Forecast spread and observed coverage')
        st.write('Mean interval width answers the question: “How wide was the forecast uncertainty across these stations?” '
                 'Observed coverage answers the question: “How often did the observations fall inside each forecast interval?”')
        summary=interval_summary(snapshot)
        st.dataframe(summary,hide_index=True,use_container_width=True)
        st.caption(f'Widths are in {spread_units}. Every interval uses the same matched stations with valid bounds for all displayed intervals. '
                   'Coverage includes interval endpoints. This storm snapshot is descriptive, not a long-term calibration assessment.')
        st.caption('Observed percentiles are interpolated between archived quantiles. Ties show an archived percentile range; '
                   'tail observations are labeled below/above the available quantiles. Tied-range midpoints are used only for map color. '
                   'p5–p95 is not a minimum–maximum range.')
        invalid=int((~snapshot.distribution_valid).sum())
        if invalid:st.warning(f'{invalid} forecasts have insufficient or crossing quantiles; their percentile/spread diagnostics are excluded.')
    st.dataframe(snapshot,hide_index=True,use_container_width=True)
    st.download_button('Download snapshot cases (CSV)',snapshot.to_csv(index=False),
        file_name=f'storm_{saved["model"]}_{saved["element"]}_{pd.Timestamp(valid):%Y%m%d%H}.csv',mime='text/csv')
with evolution:
    across='from one forecast date to the next' if daily else 'across forecast projections'
    st.write(f'Storm evolution answers the question: “How did forecast uncertainty and observed coverage change {across}?”'
             if probabilistic else f'Storm evolution answers the question: “How did forecast errors change {across}?”')
    balanced=ui.checkbox('Use stations matched on every forecast date' if daily else 'Use stations matched at every projection',key='storm_balanced')
    summary=evolution_summary(cases,balanced)
    period='forecast date' if daily else 'projection'
    st.caption(f'Each {period} uses its available stations unless the fixed-station option is enabled. Counts are shown explicitly; '
               f'interval widths and coverage use the same eligible stations within each {period}.')
    fig=plot_evolution(summary,available_intervals(cases),spread_units,date_based=daily)
    st.pyplot(fig);plt.close(fig)
    st.dataframe(summary,hide_index=True,use_container_width=True)
with detail:
    if daily:
        st.write(f'The temperature comparison answers the question: “How did forecast and observed {cfg["label"].lower()} compare for each forecast date?”')
    elif accumulation:
        st.write(f'The accumulation comparison answers the question: “How did forecast and observed {cfg["label"].lower()} totals compare over their measurement windows?”')
    else:
        st.write('The station plume answers the question: “How did the forecast and its uncertainty compare with what happened at this station?”'
                 if probabilistic else 'The station plot answers the question: “How did the forecast compare with what happened at this station?”')
    station=ui.selectbox('Station detail',station_options,
        index=station_options.index(saved['stations'][0]) if saved['stations'][0] in station_options else 0,
        key='storm_detail_station')
    if daily:
        fig=plot_temperature_periods(cases,station,saved['model'],saved['element'],saved['percentile'],
                                     saved['threshold'],saved['operator'])
    elif accumulation:
        fig=plot_accumulation_periods(cases,station,saved['model'],saved['element'],saved['percentile'],
                                     saved['threshold'],saved['operator'])
    else:
        plot_observations=result['obdf']
        if plot_observations.empty:
            st.info('No observations were loaded. The plume shows forecast information only.')
            plot_observations=pd.DataFrame({'stid':pd.Series(dtype=str),
                'valid_time':pd.Series(dtype='datetime64[ns]'),cfg['obs_value_candidates'][0]:pd.Series(dtype=float)})
        fig=plot_storm_timeseries(model_df=result['modeldf'],obs_df=plot_observations,target_station=station,
            target_init_time=result['init'],plot_start=saved['start'],plot_end=saved['end'],
            model=saved['model'],element=saved['element'],percentile=saved['percentile'],
            intervals=[('5','95'),('10','90'),('25','75')] if probabilistic else None)
    if fig is not None:
        if saved['element']=='rh':fig.axes[0].set_ylim(0,100)
        st.pyplot(fig);plt.close(fig)
    point=saved['percentile']
    st.caption((f'Point error uses p{point}; the median-error map always uses p50. ' if probabilistic else '')+
               ('Temperatures are compared by the configured forecast date. The window strip, when available, shows actual observed measurement periods; no forecast window is inferred from an archive timestamp.'
                if daily else 'Each horizontal segment represents a separate accumulation total over its window; it is not a running cumulative total. Overlapping windows are not independent verification cases.'
                if accumulation else 'The plume shows actual report timestamps; the case table records which report was matched to each forecast.'))
    st.dataframe(cases[cases.station_id.eq(station)],hide_index=True,use_container_width=True)
