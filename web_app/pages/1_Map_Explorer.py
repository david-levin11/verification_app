import streamlit as st
import pandas as pd
from pathlib import Path

from sidebar_controls import shared_sidebar_controls
from page_controls import PageControls
from station_selection import show_selected_stations
from station_metadata import normalize_station_metadata, network_elevation_controls, station_context_table

ui = PageControls("map")

from config import (
    get_map_metrics,
)

from data_loader import fetch_data
from wind_verification import filter_observed_speed
from archive_files import gust_observation_coverage
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

    return normalize_station_metadata(df)


st.title("Map Explorer")

def show_coverage_diagnostics(
    candidate_stations,
    modeldf,
    obdf,
    merged,
    station_metrics,
):
    """
    Show station/data coverage diagnostics for the current request.
    """

    candidate_set = set(str(s).strip() for s in candidate_stations)

    model_stations = (
        set(modeldf["station_id"].astype(str).str.strip())
        if "station_id" in modeldf.columns
        else set()
    )

    if "station_id" in obdf.columns:
        obs_stations = set(obdf["station_id"].astype(str).str.strip())
    elif "stid" in obdf.columns:
        obs_stations = set(obdf["stid"].astype(str).str.strip())
    else:
        obs_stations = set()

    paired_stations = (
        set(merged["station_id"].astype(str).str.strip())
        if "station_id" in merged.columns
        else set()
    )

    metric_stations = (
        set(station_metrics["station_id"].astype(str).str.strip())
        if "station_id" in station_metrics.columns
        else set()
    )

    model_only = sorted(model_stations - obs_stations)
    obs_only = sorted(obs_stations - model_stations)
    candidate_without_model = sorted(candidate_set - model_stations)
    candidate_without_obs = sorted(candidate_set - obs_stations)
    model_obs_overlap = sorted(model_stations & obs_stations)
    paired_missing_metrics = sorted(paired_stations - metric_stations)

    with st.expander("Coverage diagnostics", expanded=True):
        c1, c2, c3, c4, c5 = ui.columns(5)

        c1.metric("Candidate stations", f"{len(candidate_set):,}")
        c2.metric("Model stations", f"{len(model_stations):,}")
        c3.metric("Obs stations", f"{len(obs_stations):,}")
        c4.metric("Paired stations", f"{len(paired_stations):,}")
        c5.metric("Metric stations", f"{len(metric_stations):,}")

        st.write("Rows")
        st.dataframe(
            {
                "dataset": [
                    "modeldf",
                    "obdf",
                    "merged",
                    "station_metrics",
                ],
                "rows": [
                    len(modeldf),
                    len(obdf),
                    len(merged),
                    len(station_metrics),
                ],
            },
            use_container_width=True,
            hide_index=True,
        )

        st.write("Station coverage checks")
        st.dataframe(
            {
                "check": [
                    "Candidate stations without model data",
                    "Candidate stations without obs data",
                    "Model/obs station overlap",
                    "Paired stations missing station metrics",
                    "Model stations not in obs",
                    "Obs stations not in model",
                ],
                "count": [
                    len(candidate_without_model),
                    len(candidate_without_obs),
                    len(model_obs_overlap),
                    len(paired_missing_metrics),
                    len(model_only),
                    len(obs_only),
                ],
                "examples": [
                    ", ".join(candidate_without_model[:20]),
                    ", ".join(candidate_without_obs[:20]),
                    ", ".join(model_obs_overlap[:20]),
                    ", ".join(paired_missing_metrics[:20]),
                    ", ".join(model_only[:20]),
                    ", ".join(obs_only[:20]),
                ],
            },
            use_container_width=True,
            hide_index=True,
        )

        if "valid_time" in modeldf.columns:
            st.write(
                "Model valid time range:",
                modeldf["valid_time"].min(),
                "to",
                modeldf["valid_time"].max(),
            )

        if "valid_time" in obdf.columns:
            st.write(
                "Obs valid time range:",
                obdf["valid_time"].min(),
                "to",
                obdf["valid_time"].max(),
            )

        if "forecast_hour" in modeldf.columns:
            st.write(
                "Model forecast hours:",
                sorted(modeldf["forecast_hour"].dropna().unique().tolist())[:200],
            )
        station_coverage = pd.DataFrame(
            {
                "station_id": sorted(candidate_set),
            }
        )

        station_coverage["in_model"] = station_coverage["station_id"].isin(model_stations)
        station_coverage["in_obs"] = station_coverage["station_id"].isin(obs_stations)
        station_coverage["paired"] = station_coverage["station_id"].isin(paired_stations)
        station_coverage["has_metrics"] = station_coverage["station_id"].isin(metric_stations)

        station_coverage["coverage_status"] = "missing both"
        station_coverage.loc[
            station_coverage["in_model"] & ~station_coverage["in_obs"],
            "coverage_status",
        ] = "model only"
        station_coverage.loc[
            ~station_coverage["in_model"] & station_coverage["in_obs"],
            "coverage_status",
        ] = "obs only"
        station_coverage.loc[
            station_coverage["in_model"] & station_coverage["in_obs"] & ~station_coverage["paired"],
            "coverage_status",
        ] = "model + obs, not paired"
        station_coverage.loc[
            station_coverage["paired"],
            "coverage_status",
        ] = "paired"

        st.write("Station-level coverage")
        st.dataframe(
            station_coverage,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download station coverage CSV",
            data=station_coverage.to_csv(index=False),
            file_name="station_coverage_diagnostics.csv",
            mime="text/csv",
        )
        coverage_summary = (
            station_coverage["coverage_status"]
            .value_counts()
            .rename_axis("coverage_status")
            .reset_index(name="station_count")
        )

        st.write("Coverage status summary")
        st.dataframe(
            coverage_summary,
            use_container_width=True,
            hide_index=True,
        )
        if "valid_time" in modeldf.columns and "valid_time" in obdf.columns:
            model_times = pd.to_datetime(modeldf["valid_time"], errors="coerce")
            obs_times = pd.to_datetime(obdf["valid_time"], errors="coerce")

            model_hours = sorted(model_times.dt.hour.dropna().unique().tolist())
            obs_hours = sorted(obs_times.dt.hour.dropna().unique().tolist())

            st.write("Valid-time hour coverage")
            st.dataframe(
                {
                    "dataset": ["model", "obs"],
                    "valid_time_hours_utc": [model_hours, obs_hours],
                },
                use_container_width=True,
                hide_index=True,
            )
                # --------------------------------------------------------------
        # Possible station ID alias / prefix mismatches
        # --------------------------------------------------------------

        def strip_known_prefixes(station_id):
            station_id = str(station_id).strip()

            for prefix in ["NDBC", "COOP"]:
                if station_id.startswith(prefix):
                    return station_id[len(prefix):]

            return station_id

        model_alias = pd.DataFrame(
            {
                "model_station_id": sorted(model_stations),
            }
        )
        model_alias["canonical_station_id"] = model_alias["model_station_id"].apply(
            strip_known_prefixes
        )

        obs_alias = pd.DataFrame(
            {
                "obs_station_id": sorted(obs_stations),
            }
        )
        obs_alias["canonical_station_id"] = obs_alias["obs_station_id"].apply(
            strip_known_prefixes
        )

        alias_matches = pd.merge(
            model_alias,
            obs_alias,
            on="canonical_station_id",
            how="inner",
        )

        alias_matches = alias_matches[
            alias_matches["model_station_id"] != alias_matches["obs_station_id"]
        ]

        st.write("Possible station ID alias matches")
        st.dataframe(
            alias_matches,
            use_container_width=True,
            hide_index=True,
        )
# ---------------------------------------------------------------------
# Shared sidebar controls
# ---------------------------------------------------------------------

controls = shared_sidebar_controls(show_category_set=False, page_key="map")

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
threshold_operator = controls["threshold_operator"]
obs_time_tolerance = controls["obs_time_tolerance"]
minimum_observed_speed = controls["minimum_observed_speed"]

# ---------------------------------------------------------------------
# Map-specific sidebar controls
# ---------------------------------------------------------------------

metadata_path = ui.sidebar.text_input(
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

f1, f2, f3 = ui.columns(3)

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
    selected_zone = ui.selectbox(
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
    selected_zone = ui.selectbox(
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
    selected_zone = ui.selectbox(
        "Offshore Zone",
        zone_options,
        key="map_offshore_zone",
    )
    if selected_zone != "All":
        filtered_meta = filtered_meta[
            filtered_meta["offshore_zone_id"] == selected_zone
        ]

filtered_meta = network_elevation_controls(filtered_meta, ui, 'map')
candidate_stations = sorted(filtered_meta["station_id"].dropna().unique().tolist())

st.caption(f"{len(candidate_stations)} candidate stations from metadata filters.")
with st.expander('Matching station list'):
    st.caption('Click a column heading to sort stations, including network ID and elevation.')
    st.dataframe(station_context_table(filtered_meta), hide_index=True, use_container_width=True)


metric_options = get_map_metrics(model, element)

# If model/element changes and previous metric is invalid, reset safely.
current_metric = st.session_state.get("map_selected_metric", metric_options[0])
if current_metric not in metric_options:
    current_metric = metric_options[0]
    st.session_state["map_selected_metric"] = current_metric

selected_metric = ui.selectbox(
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
            forecast_lead_range=controls["forecast_lead_range"],
            storm_init_time=None,
            percentile_col_dict={},
            percentile=percentile,
            element=element,
            archive_root=archive_root,
            obs_time_tolerance=obs_time_tolerance,
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
            obs_time_tolerance=obs_time_tolerance,
        )

        st.write("Model rows:", len(modeldf))
        st.write("Obs rows:", len(obdf))
        st.write("Merged pair rows:", len(merged))

        before_minimum = len(merged)
        merged = filter_observed_speed(merged, minimum_observed_speed)
        if minimum_observed_speed is not None:
            st.caption(f'Observed gust ≥ {minimum_observed_speed:g} kt: {before_minimum-len(merged)} of {before_minimum} paired cases excluded.')
        if merged.empty:
            st.warning("No model/obs pairs were created.")
            st.write("Model columns:", modeldf.columns.tolist())
            st.write("Obs columns:", obdf.columns.tolist())
            st.stop()

        station_metrics = compute_station_metrics(
            merged=merged,
            station_meta=station_meta,
            threshold=threshold,
            threshold_operator=threshold_operator,
            element=element,
            probabilistic=model_is_probabilistic,
        )

        st.write("Station metrics rows:", len(station_metrics))

        if station_metrics.empty:
            st.warning("Pairs were created, but no station metrics were produced.")
            st.write("Merged columns:", merged.columns.tolist())
            st.write(merged.head(20))
            st.stop()

        # show_coverage_diagnostics(
        #     candidate_stations=candidate_stations,
        #     modeldf=modeldf,
        #     obdf=obdf,
        #     merged=merged,
        #     station_metrics=station_metrics,
        # )

        st.session_state['station_minimum_counts'] = dict(before=before_minimum,
            excluded=before_minimum-len(merged))
        st.session_state['station_gust_coverage'] = gust_observation_coverage(obdf) if element == 'gust' else None
        st.session_state["station_metrics"] = station_metrics
        st.session_state["station_metrics_context"] = {
            "model": model,
            "element": element,
            "obs": obs,
            "percentile": percentile,
            "forecast_projection": forecast_projection,
            "forecast_hours": forecast_hours,
            "forecast_lead_range": controls["forecast_lead_range"],
            "start_date": start_date,
            "end_date": end_date,
            "threshold": threshold,
            "threshold_operator": threshold_operator,
            "obs_time_tolerance": obs_time_tolerance,
            "minimum_observed_speed": minimum_observed_speed,
        }




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
            "forecast_hours": forecast_hours,
            "forecast_lead_range": controls["forecast_lead_range"],
            "start_date": start_date,
            "end_date": end_date,
            "threshold": threshold,
            "threshold_operator": threshold_operator,
            "obs_time_tolerance": obs_time_tolerance,
            "minimum_observed_speed": minimum_observed_speed,
        }

    if result_context.get('element') == 'gust' and st.session_state.get('station_gust_coverage'):
        st.caption(st.session_state['station_gust_coverage'])
    if result_context.get('minimum_observed_speed') is not None:
        counts = st.session_state.get('station_minimum_counts', {})
        st.caption(f"Observed gust ≥ {result_context['minimum_observed_speed']:g} kt; {counts.get('excluded', 0)} of {counts.get('before', 0)} paired cases excluded.")

    if result_context and result_context != current_context:
        st.info(
            "The displayed station metrics were computed with previous settings. "
            "Click **Build Station Metric Map** to refresh with the current sidebar selections."
        )

    show_map_legend(station_metrics, selected_metric)
    st.caption("Click a station to select it; click again to deselect. Selected stations have a gold outline.")
    plot_station_metric_map(station_metrics, selected_metric)
    show_selected_stations(station_meta)

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
        column_config={'mnet_id': 'Synoptic Network ID', 'elevation_ft': 'Elevation (ft)'},
    )

