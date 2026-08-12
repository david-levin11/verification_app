import streamlit as st
import pandas as pd

from config import (
    MODELS,
    PERCENTILES,
    FORECAST_PROJECTION_GROUPS,
    get_available_elements,
    get_available_obs_sources,
    get_element_config,
    get_forecast_hours,
    get_map_metrics,
    is_probabilistic,
)
from data_loader import fetch_data
from plots import plot_storm_timeseries


st.title("Storm Specific Zoom")

archive_root = st.sidebar.text_input("Local Archive Root", "../model")

model = st.sidebar.selectbox("Model", MODELS)

available_elements = get_available_elements(model)
element = st.sidebar.selectbox("Element", available_elements)

available_obs_sources = get_available_obs_sources(element)

obs = st.sidebar.selectbox(
    "Verification Source",
    available_obs_sources,
)

element_cfg = get_element_config(element)
model_is_probabilistic = is_probabilistic(model, element)

if model_is_probabilistic:
    percentile = st.sidebar.selectbox(
        "Verification Percentile",
        PERCENTILES,
        index=PERCENTILES.index(element_cfg["default_percentile"]),
    )
else:
    percentile = None

if element not in ["wind", "gust"]:
    st.warning(
        "Storm zoom is currently optimized for wind/gust plume charts. "
        "Other elements can be added after the aggregate workflow is stable."
    )

s1, s2 = st.columns(2)
storm_station = s1.text_input("Target Station", "EROWC")
storm_init_time = s2.text_input(
    "Model Init Time (YYYY-MM-DD HH:MM:SS)",
    "2026-02-21 00:00:00",
)

s3, s4 = st.columns(2)
storm_start = s3.date_input("Plot Start Date", pd.to_datetime("2026-02-21"))
storm_end = s4.date_input("Plot End Date", pd.to_datetime("2026-02-24"))

if st.button("Generate Storm Timeseries", type="primary"):
    with st.spinner(f"Fetching data for {storm_station}..."):
        modeldf, obdf, message = fetch_data(
            analysis_mode="Storm Specific Zoom",
            model=model,
            obs=obs,
            start_date=storm_start,
            end_date=storm_end,
            station_list=[storm_station.strip()],
            forecast_hours=[],
            storm_init_time=storm_init_time,
            percentile_col_dict={},
            percentile=percentile,
            element=element,
            archive_root=archive_root,
        )

    if message:
        fatal_markers = [
            "Data Missing",
            "Database error",
            "Observation Database error",
            "Observation schema error",
            "No model data",
            "No observation data",
            "No NDFD data",
            "No stations",
        ]

        if any(message.startswith(marker) for marker in fatal_markers):
            st.error(message)
            st.stop()
        else:
            st.warning(message)

        if modeldf.empty:
            st.error("No model data returned.")
            st.stop()

        if obdf.empty:
            st.error("No observation data returned.")
            st.stop()

    else:
        fig = plot_storm_timeseries(
            model_df=modeldf,
            obs_df=obdf,
            target_station=storm_station.strip(),
            target_init_time=storm_init_time,
            plot_start=storm_start,
            plot_end=storm_end,
            model=model,
        )

        if fig:
            st.pyplot(fig)
        else:
            st.warning("Could not generate chart due to missing data.")