"""Consistent controls, with independent durable settings on each page."""
import pandas as pd
import streamlit as st
from page_controls import PageControls
from archive_paths import configured_paths
from archive_availability import coverage, latest_dates, seed_dates, preflight
from forecast_archive import refs_root_control
from config import (MODELS, NDFD_EXP, EXPERIMENTAL_NATIVE_ELEMENTS, experimental_temperature, PERCENTILES, FORECAST_PROJECTION_GROUPS,
    get_available_elements, get_available_obs_sources, get_available_category_sets,
    get_element_config, get_projection_lead_bounds,
    is_probabilistic)


def shared_sidebar_controls(show_category_set=False, page_key='map'):
    ui = PageControls(page_key).sidebar
    archive_root = configured_paths()['archive_root']
    model = ui.selectbox('Model', MODELS, key='ui_model')
    refs_root=refs_root_control(ui,archive_root,model=='refs')
    elements = get_available_elements(model)
    if not elements:
        st.sidebar.error(f'No elements configured for {model}'); st.stop()
    element = ui.selectbox('Element', elements, key='ui_element')
    element_cfg = get_element_config(element)
    obs = ui.selectbox('Verification Source', get_available_obs_sources(element, model), key='ui_obs')
    model_is_probabilistic = is_probabilistic(model, element)
    percentile = None
    if model_is_probabilistic:
        percentile = ui.selectbox('Verification Percentile', PERCENTILES,
            index=PERCENTILES.index(element_cfg['default_percentile']), key='ui_percentile')
    else:
        st.sidebar.caption('Deterministic model/element: percentile verification disabled.')
    st.sidebar.markdown('### Forecast Projection')
    if model == NDFD_EXP:
        st.sidebar.caption('Experimental runs arrive intermittently. Only archived targets are verified.')
        if experimental_temperature(model, element):
            st.sidebar.caption('Temperature dates refer to the start of the archived 12-hour window. Both bounds must match.')
        if element in EXPERIMENTAL_NATIVE_ELEMENTS:
            st.sidebar.caption('Dates refer to the native window endpoint. Both archived bounds must match.')
        use_all = ui.checkbox('Use all forecast hours', value=True, key='ui_all_ndfd_exp')
    else:
        use_all = ui.checkbox('Use all forecast hours', key='ui_use_all_forecast_hours')
    projections = [p for p in FORECAST_PROJECTION_GROUPS if p != 'All']
    forecast_projection_start = forecast_projection_end = None
    forecast_hours = None
    forecast_lead_range = None
    if use_all or not projections:
        forecast_projection = 'All'
        st.sidebar.caption('Use every archived forecast projection; no cadence or lead whitelist is applied.')
    else:
        forecast_projection_start = ui.selectbox('Start projection', projections, key='ui_forecast_projection_start')
        forecast_projection_end = ui.selectbox('End projection', projections,
            index=min(2, len(projections)-1), key='ui_forecast_projection_end')
        forecast_lead_range = get_projection_lead_bounds(forecast_projection_start, forecast_projection_end)
        forecast_projection = f'{forecast_projection_start} through {forecast_projection_end}'
        low,high=forecast_lead_range
        st.sidebar.caption(f'Use all available leads {">" if low else "≥"}{low} through {high} h. Missing projections are skipped.')
    sources=[coverage(archive_root,name,element,refs_root) for name in [model,obs]]
    default_start,default_end=latest_dates(sources)
    seed_dates(page_key,[f'{page_key}_ui_start_date',f'{page_key}_ui_end_date'],
               [default_start,default_end],(model,element,obs,archive_root,refs_root))
    d1, d2 = ui.columns(2)
    start_date = d1.date_input('Start Date', default_start, key='ui_start_date')
    end_date = d2.date_input('End Date', default_end, key='ui_end_date')
    can_run=preflight(sources,start_date,end_date,st.sidebar)
    thresholds = element_cfg['thresholds']
    threshold = ui.selectbox(f"Threshold ({element_cfg['units']})", thresholds,
        index=thresholds.index(element_cfg['default_threshold']), key=f'ui_threshold_{element}')
    operators = ['>=', '>', '<=', '<']
    threshold_operator = ui.selectbox('Event definition', operators,
        index=operators.index(element_cfg.get('threshold_operator', '>=')), key=f'ui_threshold_operator_{element}',
        help='Applied consistently to forecast values, observations, and probabilities.')
    tolerance = ui.number_input('Observation time tolerance (minutes)', min_value=0, max_value=180,
        value=60, step=5, key='ui_obs_tolerance_minutes',
        help='Nearest report to the forecast valid time or accumulation endpoint; 0 requires exact matching.')
    obs_time_tolerance = f'{tolerance}min'
    st.sidebar.caption('Daily temperatures use their configured date; accumulation durations must agree.')
    minimum_observed_speed = None
    if element == 'gust':
        st.sidebar.caption('Gusts use their recorded report times and the selected observation tolerance.')
        if ui.checkbox('Set a minimum observed gust', key='ui_filter_gust'):
            minimum_observed_speed = ui.number_input('Minimum observed gust (kt)',
                min_value=0., value=5., step=1., key='ui_minimum_gust')
            st.sidebar.caption('Scores exclude lighter observed gusts, including false alarms during those cases.')
    category_set = None
    if show_category_set:
        categories = get_available_category_sets(element)
        if categories:
            category_set = ui.selectbox('Category Set', categories, key=f'ui_category_set_{element}')
    return dict(can_run=can_run,archive_root=archive_root,refs_root=refs_root, model=model, element=element, obs=obs,
        element_cfg=element_cfg, model_is_probabilistic=model_is_probabilistic, percentile=percentile,
        forecast_projection=forecast_projection, forecast_projection_start=forecast_projection_start,
        forecast_projection_end=forecast_projection_end, forecast_hours=forecast_hours, forecast_lead_range=forecast_lead_range,
        start_date=start_date, end_date=end_date, threshold=threshold,
        threshold_operator=threshold_operator, obs_time_tolerance=obs_time_tolerance, category_set=category_set,
        minimum_observed_speed=minimum_observed_speed)

