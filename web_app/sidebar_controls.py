import pandas as pd
import streamlit as st

from config import (
    MODELS,
    PERCENTILES,
    FORECAST_PROJECTION_GROUPS,
    get_available_elements,
    get_available_obs_sources,
    get_available_category_sets,
    get_element_config,
    get_forecast_hours,
    is_probabilistic,
)


def shared_sidebar_controls(show_category_set=False):
    """
    Shared sidebar controls for the verification pages.

    Returns a dictionary of selected settings.
    """

    archive_root = st.sidebar.text_input(
        "Local Archive Root",
        value=st.session_state.get("archive_root", "../model"),
        key="archive_root",
    )

    model = st.sidebar.selectbox(
        "Model",
        MODELS,
        index=MODELS.index(st.session_state.get("model", MODELS[0]))
        if st.session_state.get("model", MODELS[0]) in MODELS
        else 0,
        key="model",
    )

    available_elements = get_available_elements(model)

    # If the previous element is not valid for the newly selected model,
    # fall back to the first available element.
    current_element = st.session_state.get("element", available_elements[0])
    if current_element not in available_elements:
        current_element = available_elements[0]
        st.session_state["element"] = current_element

    element = st.sidebar.selectbox(
        "Element",
        available_elements,
        index=available_elements.index(current_element),
        key="element",
    )

    element_cfg = get_element_config(element)

    available_obs_sources = get_available_obs_sources(element)

    current_obs = st.session_state.get("obs", available_obs_sources[0])
    if current_obs not in available_obs_sources:
        current_obs = available_obs_sources[0]
        st.session_state["obs"] = current_obs

    obs = st.sidebar.selectbox(
        "Verification Source",
        available_obs_sources,
        index=available_obs_sources.index(current_obs),
        key="obs",
    )

    model_is_probabilistic = is_probabilistic(model, element)

    if model_is_probabilistic:
        default_percentile = element_cfg["default_percentile"]
        current_percentile = st.session_state.get("percentile", default_percentile)

        if current_percentile not in PERCENTILES:
            current_percentile = default_percentile
            st.session_state["percentile"] = current_percentile

        percentile = st.sidebar.selectbox(
            "Verification Percentile",
            PERCENTILES,
            index=PERCENTILES.index(current_percentile),
            key="percentile",
        )
    else:
        percentile = None
        st.session_state["percentile"] = None
        st.sidebar.caption("Deterministic model/element: percentile verification disabled.")

    forecast_projection_options = list(FORECAST_PROJECTION_GROUPS.keys())

    current_projection = st.session_state.get(
        "forecast_projection",
        forecast_projection_options[0],
    )

    if current_projection not in forecast_projection_options:
        current_projection = forecast_projection_options[0]
        st.session_state["forecast_projection"] = current_projection

    forecast_projection = st.sidebar.selectbox(
        "Forecast Projection",
        forecast_projection_options,
        index=forecast_projection_options.index(current_projection),
        key="forecast_projection",
    )

    forecast_hours = get_forecast_hours(model, element, forecast_projection)

    date_col1, date_col2 = st.sidebar.columns(2)

    start_date = date_col1.date_input(
        "Start Date",
        value=st.session_state.get(
            "start_date",
            pd.to_datetime("2025-10-01").date(),
        ),
        key="start_date",
    )

    end_date = date_col2.date_input(
        "End Date",
        value=st.session_state.get(
            "end_date",
            pd.to_datetime("2026-03-17").date(),
        ),
        key="end_date",
    )

    threshold_options = element_cfg["thresholds"]
    default_threshold = element_cfg["default_threshold"]

    current_threshold = st.session_state.get("threshold", default_threshold)

    if current_threshold not in threshold_options:
        current_threshold = default_threshold
        st.session_state["threshold"] = current_threshold

    threshold = st.sidebar.selectbox(
        f"Threshold ({element_cfg['units']})",
        threshold_options,
        index=threshold_options.index(current_threshold),
        key="threshold",
    )

    category_set = None

    if show_category_set:
        category_sets = get_available_category_sets(element)

        if category_sets:
            current_category_set = st.session_state.get(
                "category_set",
                category_sets[0],
            )

            if current_category_set not in category_sets:
                current_category_set = category_sets[0]
                st.session_state["category_set"] = current_category_set

            category_set = st.sidebar.selectbox(
                "Category Set",
                category_sets,
                index=category_sets.index(current_category_set),
                key="category_set",
            )

    return {
        "archive_root": archive_root,
        "model": model,
        "element": element,
        "obs": obs,
        "element_cfg": element_cfg,
        "model_is_probabilistic": model_is_probabilistic,
        "percentile": percentile,
        "forecast_projection": forecast_projection,
        "forecast_hours": forecast_hours,
        "start_date": start_date,
        "end_date": end_date,
        "threshold": threshold,
        "category_set": category_set,
    }