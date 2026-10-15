"""Consistent controls, with independent durable settings on each page."""
import pandas as pd
import streamlit as st
from page_controls import PageControls
from config import (MODELS, PERCENTILES, FORECAST_PROJECTION_GROUPS,
    get_available_elements, get_available_obs_sources, get_available_category_sets,
    get_element_config, get_forecast_hours, get_forecast_hours_for_projection_range,
    is_probabilistic)


def shared_sidebar_controls(show_category_set=False, page_key='map'):
    ui = PageControls(page_key).sidebar
    archive_root = ui.text_input('Local Archive Root', '../model', key='ui_archive_root')
    model = ui.selectbox('Model', MODELS, key='ui_model')
    elements = get_available_elements(model)
    if not elements:
        st.sidebar.error(f'No elements configured for {model}'); st.stop()
    element = ui.selectbox('Element', elements, key='ui_element')
    element_cfg = get_element_config(element)
    obs = ui.selectbox('Verification Source', get_available_obs_sources(element), key='ui_obs')
    model_is_probabilistic = is_probabilistic(model, element)
    percentile = None
    if model_is_probabilistic:
        percentile = ui.selectbox('Verification Percentile', PERCENTILES,
            index=PERCENTILES.index(element_cfg['default_percentile']), key='ui_percentile')
    else:
        st.sidebar.caption('Deterministic model/element: percentile verification disabled.')
    st.sidebar.markdown('### Forecast Projection')
    use_all = ui.checkbox('Use all forecast hours', key='ui_use_all_forecast_hours')
    projections = [p for p in FORECAST_PROJECTION_GROUPS if p != 'All']
    forecast_projection_start = forecast_projection_end = None
    if use_all or not projections:
        forecast_projection = 'All'
        forecast_hours = get_forecast_hours(model=model, element=element, projection='All')
    else:
        forecast_projection_start = ui.selectbox('Start projection', projections, key='ui_forecast_projection_start')
        forecast_projection_end = ui.selectbox('End projection', projections,
            index=min(2, len(projections)-1), key='ui_forecast_projection_end')
        forecast_hours = get_forecast_hours_for_projection_range(model=model, element=element,
            start_projection=forecast_projection_start, end_projection=forecast_projection_end)
        forecast_projection = f'{forecast_projection_start} through {forecast_projection_end}'
    if not forecast_hours:
        st.sidebar.warning('No configured hours in this projection range; all available hours will be used.')
        forecast_hours = None
    else:
        st.sidebar.caption(f'{forecast_projection}: {len(forecast_hours)} forecast hours')
    d1, d2 = ui.columns(2)
    start_date = d1.date_input('Start Date', pd.Timestamp('2025-10-01').date(), key='ui_start_date')
    end_date = d2.date_input('End Date', pd.Timestamp('2026-03-17').date(), key='ui_end_date')
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
    category_set = None
    if show_category_set:
        categories = get_available_category_sets(element)
        if categories:
            category_set = ui.selectbox('Category Set', categories, key=f'ui_category_set_{element}')
    return dict(archive_root=archive_root, model=model, element=element, obs=obs,
        element_cfg=element_cfg, model_is_probabilistic=model_is_probabilistic, percentile=percentile,
        forecast_projection=forecast_projection, forecast_projection_start=forecast_projection_start,
        forecast_projection_end=forecast_projection_end, forecast_hours=forecast_hours,
        start_date=start_date, end_date=end_date, threshold=threshold,
        threshold_operator=threshold_operator, obs_time_tolerance=obs_time_tolerance, category_set=category_set)
