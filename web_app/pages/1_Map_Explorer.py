import streamlit as st
import pandas as pd
from pathlib import Path

from sidebar_controls import shared_sidebar_controls

from config import (
    get_map_metrics,
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

# ---------------------------------------------------------------------
# Shared sidebar controls
# ---------------------------------------------------------------------

controls = shared_sidebar_controls(show_category_set=False)

archive_root = controls["archive_root"]
model = controls["model"]
element = controls["element"]
obs = controls["obs"]
element_cfg = controls["element_cfg"]
model_is_probabilistic = controls["model_is_probabilistic"]
percentile = controls["percentile"]
forecast_projection = controls["forecast_projection"]
forecast_hours = controls["forecast_hours"]
start_date = controls["start_date"]
end_date = controls["end_date"]
threshold = controls["threshold"]

# ---------------------------------------------------------------------
# Map-specific sidebar controls
# ---------------------------------------------------------------------

metadata_path = st.sidebar.text_input(
    "Station Metadata Path",
    value=st.session_state.get(
        "metadata_path",
        "../metadata/ak_station_metadata.parquet",
    ),
    key="metadata_path",
)

station_meta = load_station_metadata(metadata_path)

if station_meta.empty:
    st.error("Station metadata file not found or empty.")
    st.stop()

st.markdown(
    "Use metadata filters to choose candidate stations, then compute site-level verification metrics."
)

# ---------------------------------------------------------------------
# Metadata filters
# ---------------------------------------------------------------------

f1, f2, f3 = st.columns(3)

context_options = ["All"]
if "station_context" in station_meta.columns:
    context_options += sorted(station_meta["station_context"].dropna().unique().tolist())

selected_context = f1.selectbox(
    "Station Context",
    context_options,
    key="map_station_context",
)

wfo_options = ["All"]
if "wfo_best" in station_meta.columns:
    wfo_options += sorted(station_meta["wfo_best"].dropna().unique().tolist())

selected_wfo = f2.selectbox(
    "WFO",
    wfo_options,
    key="map_wfo",
)

zone_type = f3.selectbox(
    "Zone Filter Type",
    ["None", "Public Zone", "Coastal Marine Zone", "Offshore Zone"],
    key="map_zone_type",
)

filtered_meta = station_meta.copy()

if selected_context != "All" and "station_context" in filtered_meta.columns:
    filtered_meta = filtered_meta[filtered_meta["station_context"] == selected_context]

if selected_wfo != "All" and "wfo_best" in filtered_meta.columns:
    filtered_meta = filtered_meta[filtered_meta["wfo_best"] == selected_wfo]

if zone_type == "Public Zone" and "public_zone_id" in filtered_meta.columns:
    zone_options = ["All"] + sorted(
        filtered_meta["public_zone_id"].dropna().unique().tolist()
    )
    selected_zone = st.selectbox(
        "Public Zone",
        zone_options,
        key="map_public_zone",
    )
    if selected_zone != "All":
        filtered_meta = filtered_meta[filtered_meta["public_zone_id"] == selected_zone]

elif zone_type == "Coastal Marine Zone" and "coastal_marine_zone_id" in filtered_meta.columns:
    zone_options = ["All"] + sorted(
        filtered_meta["coastal_marine_zone_id"].dropna().unique().tolist()
    )
    selected_zone = st.selectbox(
        "Coastal Marine Zone",
        zone_options,
        key="map_coastal_marine_zone",
    )
    if selected_zone != "All":
        filtered_meta = filtered_meta[
            filtered_meta["coastal_marine_zone_id"] == selected_zone
        ]

elif zone_type == "Offshore Zone" and "offshore_zone_id" in filtered_meta.columns:
    zone_options = ["All"] + sorted(
        filtered_meta["offshore_zone_id"].dropna().unique().tolist()
    )
    selected_zone = st.selectbox(
        "Offshore Zone",
        zone_options,
        key="map_offshore_zone",
    )
    if selected_zone != "All":
        filtered_meta = filtered_meta[
            filtered_meta["offshore_zone_id"] == selected_zone
        ]

candidate_stations = sorted(filtered_meta["station_id"].dropna().unique().tolist())

st.caption(f"{len(candidate_stations)} candidate stations from metadata filters.")

max_stations = st.number_input(
    "Maximum stations to query",
    min_value=1,
    max_value=300,
    value=min(300, max(1, len(candidate_stations))),
    step=25,
    key="map_max_stations",
)

candidate_stations = candidate_stations[: int(max_stations)]

metric_options = get_map_metrics(model, element)

# If model/element changes and previous metric is invalid, reset safely.
current_metric = st.session_state.get("map_selected_metric", metric_options[0])
if current_metric not in metric_options:
    current_metric = metric_options[0]
    st.session_state["map_selected_metric"] = current_metric

selected_metric = st.selectbox(
    "Map Metric",
    metric_options,
    index=metric_options.index(current_metric),
    key="map_selected_metric",
)

# ---------------------------------------------------------------------
# Fetch and compute
# ---------------------------------------------------------------------

if st.button("Build Station Metric Map", type="primary"):
    with st.spinner("Fetching data and computing station-level verification metrics..."):
        modeldf, obdf, message = fetch_data(
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

        merged = build_verification_pairs(
            modeldf=modeldf,
            obdf=obdf,
            model=model,
            obs=obs,
            element=element,
            percentile=percentile,
        )

        st.write("Model rows:", len(modeldf))
        st.write("Obs rows:", len(obdf))
        st.write("Merged pair rows:", len(merged))

        if merged.empty:
            st.warning("No model/obs pairs were created.")
            st.write("Model columns:", modeldf.columns.tolist())
            st.write("Obs columns:", obdf.columns.tolist())
            st.stop()

        station_metrics = compute_station_metrics(
            merged=merged,
            station_meta=station_meta,
            threshold=threshold,
        )

        st.write("Station metrics rows:", len(station_metrics))

        if station_metrics.empty:
            st.warning("Pairs were created, but no station metrics were produced.")
            st.write("Merged columns:", merged.columns.tolist())
            st.write(merged.head(20))
            st.stop()

        st.session_state["station_metrics"] = station_metrics
        st.session_state["station_metrics_context"] = {
            "model": model,
            "element": element,
            "obs": obs,
            "percentile": percentile,
            "forecast_projection": forecast_projection,
            "start_date": start_date,
            "end_date": end_date,
            "threshold": threshold,
        }

        st.session_state["selected_station_list"] = sorted(
            station_metrics["station_id"].head(5).tolist()
        )


# ---------------------------------------------------------------------
# Display previous/current results
# ---------------------------------------------------------------------

if "station_metrics" in st.session_state:
    station_metrics = st.session_state["station_metrics"]

    st.subheader("Station Metric Map")

    # Warn if the displayed map was computed with different settings.
    result_context = st.session_state.get("station_metrics_context", {})
    current_context = {
        "model": model,
        "element": element,
        "obs": obs,
        "percentile": percentile,
        "forecast_projection": forecast_projection,
        "start_date": start_date,
        "end_date": end_date,
        "threshold": threshold,
    }

    if result_context and result_context != current_context:
        st.info(
            "The displayed station metrics were computed with previous settings. "
            "Click **Build Station Metric Map** to refresh with the current sidebar selections."
        )

    show_map_legend(station_metrics, selected_metric)
    plot_station_metric_map(station_metrics, selected_metric)

    st.subheader("Station Metrics Table")

    if station_metrics.empty:
        st.warning(
            "No station metrics were produced. Check whether model/obs pairs were created."
        )
        st.stop()

    if selected_metric not in station_metrics.columns:
        st.warning(
            f"Selected metric '{selected_metric}' is not available. "
            f"Available columns: {station_metrics.columns.tolist()}"
        )
        st.dataframe(station_metrics, use_container_width=True, hide_index=True)
        st.stop()

    st.dataframe(
        station_metrics.sort_values(selected_metric, ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    selected_stations = st.multiselect(
        "Stations to use in Aggregate Verification",
        options=sorted(station_metrics["station_id"].unique().tolist()),
        default=st.session_state.get(
            "selected_station_list",
            sorted(station_metrics["station_id"].head(5).tolist()),
        ),
        key="map_selected_station_multiselect",
    )

    st.session_state["selected_station_list"] = selected_stations