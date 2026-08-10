import streamlit as st
import pandas as pd
from pathlib import Path

from config import (
    MODELS,
    OBS_SOURCES,
    PERCENTILES,
    FORECAST_PROJECTION_GROUPS,
    get_available_elements,
    get_element_config,
    get_forecast_hours,
    get_map_metrics,
    is_probabilistic,
)
from data_loader import fetch_data
from pairing import build_verification_pairs
from metrics import compute_station_metrics
from maps import plot_station_metric_map, show_map_legend


@st.cache_data
def load_station_metadata(metadata_path):
    metadata_path = Path(metadata_path)

    if not metadata_path.exists():
        return pd.DataFrame()

    if metadata_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(metadata_path)
    else:
        df = pd.read_csv(metadata_path)

    if "station_id" in df.columns:
        df["station_id"] = df["station_id"].astype(str).str.strip()

    return df


st.title("Map Explorer")

archive_root = st.sidebar.text_input("Local Archive Root", "../model")
metadata_path = st.sidebar.text_input(
    "Station Metadata Path",
    "../metadata/ak_station_metadata.parquet",
)

station_meta = load_station_metadata(metadata_path)

model = st.sidebar.selectbox("Model", MODELS)

available_elements = get_available_elements(model)
element = st.sidebar.selectbox("Element", available_elements)

obs = st.sidebar.selectbox("Verification Source", OBS_SOURCES)

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
    st.sidebar.caption("Deterministic model/element: percentile verification disabled.")

forecast_projection = st.sidebar.selectbox(
    "Forecast Projection",
    list(FORECAST_PROJECTION_GROUPS.keys()),
)

forecast_hours = get_forecast_hours(model, element, forecast_projection)

date_col1, date_col2 = st.sidebar.columns(2)
start_date = date_col1.date_input("Start Date", pd.to_datetime("2025-10-01"))
end_date = date_col2.date_input("End Date", pd.to_datetime("2026-03-17"))

threshold = st.sidebar.selectbox(
    f"Threshold ({element_cfg['units']})",
    element_cfg["thresholds"],
    index=element_cfg["thresholds"].index(element_cfg["default_threshold"]),
)

if station_meta.empty:
    st.error("Station metadata file not found or empty.")
    st.stop()

st.markdown(
    "Use metadata filters to choose candidate stations, then compute site-level verification metrics."
)

f1, f2, f3 = st.columns(3)

context_options = ["All"]
if "station_context" in station_meta.columns:
    context_options += sorted(station_meta["station_context"].dropna().unique().tolist())

selected_context = f1.selectbox("Station Context", context_options)

wfo_options = ["All"]
if "wfo_best" in station_meta.columns:
    wfo_options += sorted(station_meta["wfo_best"].dropna().unique().tolist())

selected_wfo = f2.selectbox("WFO", wfo_options)

zone_type = f3.selectbox(
    "Zone Filter Type",
    ["None", "Public Zone", "Coastal Marine Zone", "Offshore Zone"],
)

filtered_meta = station_meta.copy()

if selected_context != "All" and "station_context" in filtered_meta.columns:
    filtered_meta = filtered_meta[filtered_meta["station_context"] == selected_context]

if selected_wfo != "All" and "wfo_best" in filtered_meta.columns:
    filtered_meta = filtered_meta[filtered_meta["wfo_best"] == selected_wfo]

if zone_type == "Public Zone" and "public_zone_id" in filtered_meta.columns:
    zone_options = ["All"] + sorted(filtered_meta["public_zone_id"].dropna().unique().tolist())
    selected_zone = st.selectbox("Public Zone", zone_options)
    if selected_zone != "All":
        filtered_meta = filtered_meta[filtered_meta["public_zone_id"] == selected_zone]

elif zone_type == "Coastal Marine Zone" and "coastal_marine_zone_id" in filtered_meta.columns:
    zone_options = ["All"] + sorted(filtered_meta["coastal_marine_zone_id"].dropna().unique().tolist())
    selected_zone = st.selectbox("Coastal Marine Zone", zone_options)
    if selected_zone != "All":
        filtered_meta = filtered_meta[filtered_meta["coastal_marine_zone_id"] == selected_zone]

elif zone_type == "Offshore Zone" and "offshore_zone_id" in filtered_meta.columns:
    zone_options = ["All"] + sorted(filtered_meta["offshore_zone_id"].dropna().unique().tolist())
    selected_zone = st.selectbox("Offshore Zone", zone_options)
    if selected_zone != "All":
        filtered_meta = filtered_meta[filtered_meta["offshore_zone_id"] == selected_zone]

candidate_stations = sorted(filtered_meta["station_id"].dropna().unique().tolist())

st.caption(f"{len(candidate_stations)} candidate stations from metadata filters.")

max_stations = st.number_input(
    "Maximum stations to query",
    min_value=1,
    max_value=300,
    value=min(300, max(1, len(candidate_stations))),
    step=25,
)

candidate_stations = candidate_stations[:int(max_stations)]

metric_options = get_map_metrics(model, element)
selected_metric = st.selectbox("Map Metric", metric_options, index=0)

if st.button("Build Station Metric Map", type="primary"):
    with st.spinner("Fetching data and computing station-level verification metrics..."):
        modeldf, obdf, error_msg = fetch_data(
            analysis_mode="Aggregate Verification",
            model=model,
            obs=obs,
            start_date=start_date,
            end_date=end_date,
            station_list=candidate_stations,
            forecast_hours=forecast_hours,
            storm_init_time=None,
            percentile_col_dict={},
            percentile=percentile,
            element=element,
            archive_root=archive_root,
        )

        if error_msg:
            st.error(error_msg)
            st.stop()

        merged = build_verification_pairs(
            modeldf=modeldf,
            obdf=obdf,
            model=model,
            obs=obs,
            element=element,
            percentile=percentile,
        )

        station_metrics = compute_station_metrics(
            merged=merged,
            station_meta=station_meta,
            threshold=threshold,
        )

        st.session_state["station_metrics"] = station_metrics
        st.session_state["selected_station_list"] = candidate_stations[:5]

if "station_metrics" in st.session_state:
    station_metrics = st.session_state["station_metrics"]

    st.subheader("Station Metric Map")
    show_map_legend(station_metrics, selected_metric)
    plot_station_metric_map(station_metrics, selected_metric)

    st.subheader("Station Metrics Table")
    st.dataframe(
        station_metrics.sort_values(selected_metric, ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    selected_stations = st.multiselect(
        "Stations to use in Aggregate Verification",
        options=sorted(station_metrics["station_id"].unique().tolist()),
        default=sorted(station_metrics["station_id"].head(5).tolist()),
    )

    st.session_state["selected_station_list"] = selected_stations