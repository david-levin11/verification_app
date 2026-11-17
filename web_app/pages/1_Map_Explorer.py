from data_downloads import DataDownloads
downloads = DataDownloads('map')
from archive_paths import configured_paths
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
from color_scales import scale_controls, scale_units, clipping_caption


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

def show_coverage_diagnostics(candidate_stations,modeldf,obdf,merged,station_metrics):
    candidate=set(map(str,candidate_stations))
    model_sites=set(modeldf.get('station_id',[]))
    obs_sites=set(obdf.get('station_id',obdf.get('stid',[])))
    paired=set(merged.get('station_id',[]))
    table=pd.DataFrame({'station_id':sorted(candidate)})
    table['has_model']=table.station_id.isin(model_sites)
    table['has_observation']=table.station_id.isin(obs_sites)
    table['has_matched_cases']=table.station_id.isin(paired)
    counts=pd.DataFrame({'dataset':['Forecasts','Observations','Matched cases','Station metrics'],
        'rows':[len(modeldf),len(obdf),len(merged),len(station_metrics)]})
    return table,counts

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

metadata_path = configured_paths()['metadata_path']

station_meta = load_station_metadata(metadata_path)

if station_meta.empty:
    downloads.issue("Station metadata file not found or empty.", fatal=True)
    downloads.stop()

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
downloads.add(station_context_table(filtered_meta), name='Matching stations')


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

if st.button("Build Station Metric Map", type="primary", disabled=not controls["can_run"]):
    try:
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
                refs_root=controls['refs_root'],
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
                    downloads.issue(message, fatal=True)
                    downloads.stop()
                else:
                    downloads.issue(message)

            if modeldf.empty:
                downloads.issue("No model data returned.", fatal=True)
                downloads.stop()

            if obdf.empty:
                downloads.issue("No observation data returned.", fatal=True)
                downloads.stop()

            merged = build_verification_pairs(
                modeldf=modeldf,
                obdf=obdf,
                model=model,
                obs=obs,
                element=element,
                percentile=percentile,
                obs_time_tolerance=obs_time_tolerance,
            )


            before_minimum = len(merged)
            merged = filter_observed_speed(merged, minimum_observed_speed)
            if minimum_observed_speed is not None:
                st.caption(f'Observed gust ≥ {minimum_observed_speed:g} kt: {before_minimum-len(merged)} of {before_minimum} paired cases excluded.')
            if merged.empty:
                st.warning("No model/obs pairs were created.")
                downloads.stop()

            station_metrics = compute_station_metrics(
                merged=merged,
                station_meta=station_meta,
                threshold=threshold,
                threshold_operator=threshold_operator,
                element=element,
                probabilistic=model_is_probabilistic,
            )


            if station_metrics.empty:
                st.warning("Pairs were created, but no station metrics were produced.")
                downloads.add(merged,name="Unscored paired cases")
                downloads.stop()

            st.session_state['station_coverage_tables']=show_coverage_diagnostics(
                candidate_stations,modeldf,obdf,merged,station_metrics)

            st.session_state['station_minimum_counts'] = dict(before=before_minimum,
                excluded=before_minimum-len(merged))
            st.session_state['station_gust_coverage'] = gust_observation_coverage(obdf) if element == 'gust' else None
            st.session_state["station_metrics"] = station_metrics
            st.session_state["station_metrics_context"] = {
                "model": model,
                "archive_root": archive_root,
                "refs_root": controls["refs_root"],
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
    except Exception as exc:
        downloads.issue(str(exc),fatal=True)




# ---------------------------------------------------------------------
# Display previous/current results
# ---------------------------------------------------------------------

if "station_metrics" in st.session_state:
    station_metrics = st.session_state["station_metrics"]
    for table,name in zip(st.session_state.get('station_coverage_tables',[]),['Station coverage','Coverage counts']):
        downloads.add(table,name=name)

    st.subheader("Station Metric Map")

    # Warn if the displayed map was computed with different settings.
    result_context = st.session_state.get("station_metrics_context", {})
    current_context = {
            "model": model,
            "archive_root": archive_root,
            "refs_root": controls["refs_root"],
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

    limits = None
    if not station_metrics.empty and selected_metric in station_metrics:
        display_element = result_context.get('element', element)
        plotted_metrics = station_metrics.dropna(subset=[c for c in ['latitude','longitude',selected_metric] if c in station_metrics])
        limits = scale_controls(ui, plotted_metrics[selected_metric], display_element, selected_metric)
    st.caption("Click a station to select it; click again to deselect. Selected stations have a gold outline.")
    plot_station_metric_map(station_metrics, selected_metric, limits)
    if limits is not None:
        show_map_legend(plotted_metrics, selected_metric, limits, scale_units(display_element, selected_metric))
        clipping_caption(plotted_metrics[selected_metric], limits)
    show_selected_stations(station_meta)


    if station_metrics.empty:
        st.warning(
            "No station metrics were produced. Check whether model/obs pairs were created."
        )
        downloads.stop()

    if selected_metric not in station_metrics.columns:
        st.warning(
            f"Selected metric '{selected_metric}' is not available. "
            f"Available columns: {station_metrics.columns.tolist()}"
        )
        downloads.add(station_metrics, use_container_width=True, hide_index=True, name='Station metrics')
        downloads.stop()

    downloads.add(
        station_metrics.sort_values(selected_metric, ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={'mnet_id': 'Synoptic Network ID', 'elevation_ft': 'Elevation (ft)'}, name='Station metrics')




downloads.render()
