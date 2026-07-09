import streamlit as st
import pydeck as pdk
import pandas as pd
import numpy as np
from pathlib import Path
from data_loader import fetch_data
from plots import (
    plot_storm_timeseries,  
    plot_forecast_bias_bar_chart,
    plot_confusion_matrix,
    plot_threshold_reliability,
    plot_quantile_rank_histogram
)

# Streamlit Page Configuration
st.set_page_config(page_title="Weather Verification", layout="wide")

# --- Configuration Dictionaries ---
fcst_hrs_dict = {
    'nbmqmd_exp': {"Day1": [6,12,18,24], "Day2": [30,36,42,48], "Day3": [52,58,66,72], "Day4": [84,96,108,120]}
}
percentile_col_dict = {
    "nbmqmd_exp": {
        "5": "wind_p5",
        "10": "wind_p10",
        "25": "wind_p25",
        "50": "wind_p50",
        "75": "wind_p75",
        "90": "wind_p90",
        "95": "wind_p95",
    },
    "nbmqmd": {
        "5": "wind_p5",
        "10": "wind_p10",
        "25": "wind_p25",
        "50": "wind_p50",
        "75": "wind_p75",
        "90": "wind_p90",
        "95": "wind_p95",
    },
}

beaufort_bins = [-0.1, 1, 3, 6, 10, 16, 21, 27, 33, 40, 47, 55, 63, np.inf]
beaufort_labels = {0: "Calm", 1: "Light Air", 2: "Light Breeze", 3: "Gentle Breeze", 4: "Moderate Breeze", 
                   5: "Fresh Breeze", 6: "Strong Breeze", 7: "Near Gale", 8: "Gale", 9: "Strong Gale", 
                   10: "Storm", 11: "Violent Storm", 12: "Hurricane"}
marine_criteria_bins = [-0.1, 25, 33, 48, 63]
marine_criteria_labels = {0: "None", 1: "SCA", 2: "Gale", 3: "Storm"}

category_labels_dict = {
    "Marine Category": [marine_criteria_bins, marine_criteria_labels, list(marine_criteria_labels.keys()), "marine_cat_model", "marine_cat_obs"],
    "Beaufort Category": [beaufort_bins, beaufort_labels, list(beaufort_labels.keys()), "beaufort_cat_model", "beaufort_cat_obs"]
}
# ==========================================
# HELPER FUNCTIONS
# ==========================================
@st.cache_data
def load_station_metadata(metadata_path):
    """
    Load station metadata created from Synoptic + NWS zones.
    """
    metadata_path = Path(metadata_path)

    if not metadata_path.exists():
        return pd.DataFrame()

    if metadata_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(metadata_path)
    else:
        df = pd.read_csv(metadata_path)

    # Standardize station ID
    if "station_id" in df.columns:
        df["station_id"] = df["station_id"].astype(str).str.strip()

    return df

def show_map_legend(station_metrics, metric):
    """
    Display a simple color legend for the pydeck station metric map.
    """
    if station_metrics.empty or metric not in station_metrics.columns:
        return

    values = station_metrics[metric].dropna()

    if values.empty:
        return

    metric_min = values.min()
    metric_mid = values.median()
    metric_max = values.max()

    st.markdown(
        f"""
        <div style="margin-top: 0.5rem; margin-bottom: 0.75rem;">
            <div style="font-weight: 600; margin-bottom: 0.25rem;">
                Map color scale: {metric}
            </div>
            <div style="
                height: 18px;
                width: 100%;
                background: linear-gradient(
                    to right,
                    rgb(80,160,220),
                    rgb(168,110,130),
                    rgb(255,60,40)
                );
                border: 1px solid #999;
                border-radius: 4px;
            "></div>
            <div style="
                display: flex;
                justify-content: space-between;
                font-size: 0.85rem;
                margin-top: 0.15rem;
            ">
                <span>Low: {metric_min:.2f}</span>
                <span>Median: {metric_mid:.2f}</span>
                <span>High: {metric_max:.2f}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def make_verification_pairs(
    modeldf,
    obdf,
    obs,
    criteria,
    category_labels_dict,
):
    """
    Merge model and observation data into forecast/observation pairs.

    Returns:
        merged dataframe
        raw observation wind column name
    """
    raw_obs_col = "obs_wind_speed_kts" if "obs_wind_speed_kts" in obdf.columns else "wind_speed_kt"

    model_category_col = category_labels_dict[criteria][3]
    obs_category_col = category_labels_dict[criteria][4]

    modeldf = modeldf.copy()
    obdf = obdf.copy()

    modeldf[model_category_col] = pd.cut(
        modeldf["wind_speed_kt"],
        bins=category_labels_dict[criteria][0],
        labels=category_labels_dict[criteria][2],
    )

    obdf[obs_category_col] = pd.cut(
        obdf[raw_obs_col],
        bins=category_labels_dict[criteria][0],
        labels=category_labels_dict[criteria][2],
    )

    if obs == "obs":
        obdf.rename(columns={"stid": "station_id"}, inplace=True, errors="ignore")

        modeldf["valid_time"] = modeldf["valid_time"].astype("datetime64[ns]")
        obdf["valid_time"] = obdf["valid_time"].astype("datetime64[ns]")

        modeldf = modeldf.sort_values(["valid_time", "station_id", "forecast_hour"])
        obdf = obdf.sort_values(["valid_time", "station_id"])

        merged = pd.merge_asof(
            modeldf,
            obdf,
            on="valid_time",
            by="station_id",
            direction="nearest",
            tolerance=pd.Timedelta("1H"),
        )

    else:
        # For URMA, preserve station_id if available.
        keep_cols = ["valid_time", "wind_speed_kt", obs_category_col]
        if "station_id" in obdf.columns:
            keep_cols.insert(0, "station_id")

        if "station_id" in obdf.columns and "station_id" in modeldf.columns:
            merged = pd.merge(
                modeldf,
                obdf[keep_cols],
                on=["valid_time", "station_id"],
                suffixes=("_model", "_obs"),
            )
        else:
            merged = pd.merge(
                modeldf,
                obdf[keep_cols],
                on="valid_time",
                suffixes=("_model", "_obs"),
            )

    merged[obs_category_col] = pd.to_numeric(merged[obs_category_col], errors="coerce")
    merged[model_category_col] = pd.to_numeric(merged[model_category_col], errors="coerce")

    return merged, raw_obs_col

def compute_station_metrics(
    merged,
    station_meta,
    threshold,
    raw_obs_col,
    model_value_col="wind_speed_kt",
):
    """
    Compute site-level verification metrics for map/table display.
    """
    df = merged.copy()

    if "station_id" not in df.columns:
        return pd.DataFrame()

    # Determine model/obs columns after merge.
    if model_value_col not in df.columns:
        if "wind_speed_kt_model" in df.columns:
            model_value_col = "wind_speed_kt_model"
        else:
            return pd.DataFrame()

    if raw_obs_col not in df.columns:
        if "wind_speed_kt_obs" in df.columns:
            raw_obs_col = "wind_speed_kt_obs"
        elif "obs_wind_speed_kts" in df.columns:
            raw_obs_col = "obs_wind_speed_kts"
        else:
            return pd.DataFrame()

    df = df.dropna(subset=["station_id", model_value_col, raw_obs_col]).copy()

    if df.empty:
        return pd.DataFrame()

    df["error"] = df[model_value_col] - df[raw_obs_col]
    df["abs_error"] = df["error"].abs()
    df["sq_error"] = df["error"] ** 2

    df["obs_event"] = df[raw_obs_col] >= threshold
    df["fcst_event"] = df[model_value_col] >= threshold

    grouped = df.groupby("station_id").agg(
        n=("error", "count"),
        bias=("error", "mean"),
        mae=("abs_error", "mean"),
        rmse=("sq_error", lambda x: np.sqrt(np.mean(x))),
        mean_obs=(raw_obs_col, "mean"),
        mean_fcst=(model_value_col, "mean"),
        max_obs=(raw_obs_col, "max"),
        max_fcst=(model_value_col, "max"),
        event_hits=("obs_event", lambda x: np.nan),  # placeholder removed below
    ).reset_index()

    # Contingency metrics per station
    contingency_rows = []

    for station_id, sdf in df.groupby("station_id"):
        hits = ((sdf["fcst_event"]) & (sdf["obs_event"])).sum()
        misses = ((~sdf["fcst_event"]) & (sdf["obs_event"])).sum()
        false_alarms = ((sdf["fcst_event"]) & (~sdf["obs_event"])).sum()
        correct_negatives = ((~sdf["fcst_event"]) & (~sdf["obs_event"])).sum()

        pod = hits / (hits + misses) if (hits + misses) > 0 else np.nan
        far = false_alarms / (hits + false_alarms) if (hits + false_alarms) > 0 else np.nan
        csi = hits / (hits + misses + false_alarms) if (hits + misses + false_alarms) > 0 else np.nan
        event_freq_obs = (hits + misses) / len(sdf) if len(sdf) > 0 else np.nan
        event_freq_fcst = (hits + false_alarms) / len(sdf) if len(sdf) > 0 else np.nan

        contingency_rows.append(
            {
                "station_id": station_id,
                "hits": hits,
                "misses": misses,
                "false_alarms": false_alarms,
                "correct_negatives": correct_negatives,
                "pod": pod,
                "far": far,
                "csi": csi,
                "event_freq_obs": event_freq_obs,
                "event_freq_fcst": event_freq_fcst,
            }
        )

    cont = pd.DataFrame(contingency_rows)

    metrics = grouped.drop(columns=["event_hits"], errors="ignore").merge(
        cont,
        on="station_id",
        how="left",
    )

    # Join metadata
    if not station_meta.empty:
        meta_cols = [
            c for c in [
                "station_id",
                "name",
                "latitude",
                "longitude",
                "elevation_ft",
                "wfo_best",
                "public_zone_id",
                "public_zone_name",
                "coastal_marine_zone_id",
                "coastal_marine_zone_name",
                "offshore_zone_id",
                "offshore_zone_name",
                "station_context",
            ]
            if c in station_meta.columns
        ]

        metrics = metrics.merge(
            station_meta[meta_cols].drop_duplicates(subset=["station_id"]),
            on="station_id",
            how="left",
        )

    metrics = metrics.dropna(subset=["latitude", "longitude"], how="any")

    return metrics

def plot_station_metric_map(station_metrics, metric):
    """
    Display station metrics on a pydeck map.
    """
    if station_metrics.empty:
        st.warning("No station metrics available to map.")
        return

    map_df = station_metrics.copy()

    if metric not in map_df.columns:
        st.warning(f"Metric '{metric}' not found in station metrics.")
        return

    map_df = map_df.dropna(subset=["latitude", "longitude", metric]).copy()

    if map_df.empty:
        st.warning(f"No valid values available for metric: {metric}")
        return

    # Normalize metric for radius/color scaling
    metric_min = map_df[metric].min()
    metric_max = map_df[metric].max()

    if metric_max == metric_min:
        map_df["metric_scaled"] = 0.5
    else:
        map_df["metric_scaled"] = (map_df[metric] - metric_min) / (metric_max - metric_min)

    # Simple blue-orange-red style via RGB values
    # Low values lighter, high values darker/redder.
    map_df["r"] = (80 + 175 * map_df["metric_scaled"]).astype(int)
    map_df["g"] = (160 - 100 * map_df["metric_scaled"]).clip(40, 180).astype(int)
    map_df["b"] = (220 - 180 * map_df["metric_scaled"]).clip(40, 220).astype(int)
    map_df["a"] = 180

    map_df["radius"] = 6000 + 10000 * map_df["metric_scaled"]

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[longitude, latitude]",
        get_fill_color="[r, g, b, a]",
        get_radius="radius",
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        latitude=float(map_df["latitude"].mean()),
        longitude=float(map_df["longitude"].mean()),
        zoom=3.5,
        pitch=0,
    )

    tooltip = {
        "html": """
        <b>{station_id}</b><br/>
        {name}<br/>
        <b>n:</b> {n}<br/>
        <b>Bias:</b> {bias}<br/>
        <b>MAE:</b> {mae}<br/>
        <b>RMSE:</b> {rmse}<br/>
        <b>POD:</b> {pod}<br/>
        <b>FAR:</b> {far}<br/>
        <b>CSI:</b> {csi}<br/>
        <b>Public Zone:</b> {public_zone_id} {public_zone_name}<br/>
        <b>Marine Zone:</b> {coastal_marine_zone_id} {coastal_marine_zone_name}
        """,
        "style": {"backgroundColor": "white", "color": "black"},
    }

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="light",
    )

    st.pydeck_chart(deck, use_container_width=True)

def apply_wind_direction_filter(
    merged,
    use_dir_filter,
    min_dir=None,
    max_dir=None,
):
    """
    Filter verification pairs by observed wind direction.

    Handles directions crossing north, e.g. 315° to 45°.
    """
    if not use_dir_filter:
        return merged

    dir_candidates = [
        "obs_wind_dir_deg",
        "wind_dir",
        "wind_direction",
        "wind_direction_obs",
    ]

    dir_col_name = next(
        (col for col in dir_candidates if col in merged.columns),
        None,
    )

    if dir_col_name is None:
        st.warning("Could not find an observed wind direction column. Proceeding with all data.")
        return merged

    filtered = merged.copy()

    if min_dir <= max_dir:
        filtered = filtered[
            (filtered[dir_col_name] >= min_dir)
            & (filtered[dir_col_name] <= max_dir)
        ]
    else:
        filtered = filtered[
            (filtered[dir_col_name] >= min_dir)
            | (filtered[dir_col_name] <= max_dir)
        ]

    st.info(
        f"Filtered to observed wind directions between {min_dir}° and {max_dir}°. "
        f"({len(filtered)} valid pairs remain)."
    )

    if filtered.empty:
        st.error("No data points fell within that wind direction range.")
        st.stop()

    return filtered
# ==========================================
# SIDEBAR: Global Settings
# ==========================================
st.sidebar.title("Global Settings")

archive_root = st.sidebar.text_input("Local Archive Root", "../model")
metadata_path = st.sidebar.text_input(
    "Station Metadata Path",
    "../metadata/ak_station_metadata.parquet",
)

station_meta = load_station_metadata(metadata_path)

st.sidebar.markdown("---")

model = st.sidebar.selectbox("Model", ["nbmqmd_exp", "nbmqmd", "nbm", "hrrr", "ndfd"])
obs = st.sidebar.selectbox("Verification Source", ["obs", "urma"])
element = st.sidebar.selectbox("Element", ["wind"], index=0)

if model in ["nbmqmd", "nbmqmd_exp"]:
    percentile = st.sidebar.selectbox(
        "Verification Percentile",
        ["5", "10", "25", "50", "75", "90", "95"],
        index=4,
    )
else:
    percentile = "50"

forecast_projection = st.sidebar.selectbox(
    "Forecast Projection",
    ["Day1", "Day2", "Day3", "Day4", "Day5", "Day6", "Day7"],
)

date_col1, date_col2 = st.sidebar.columns(2)
global_start_date = date_col1.date_input("Start Date", pd.to_datetime("2025-10-01"))
global_end_date = date_col2.date_input("End Date", pd.to_datetime("2026-03-17"))

wind_threshold = st.sidebar.number_input("Wind Threshold (kts)", value=25)

criteria = st.sidebar.selectbox(
    "Verification Criteria",
    ["Marine Category", "Beaufort Category"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Wind Direction Filter")

use_dir_filter = st.sidebar.checkbox("Filter by Observed Wind Direction?")

if use_dir_filter:
    min_dir = st.sidebar.number_input(
        "Minimum Direction (Degrees)",
        min_value=0,
        max_value=360,
        value=315,
    )

    max_dir = st.sidebar.number_input(
        "Maximum Direction (Degrees)",
        min_value=0,
        max_value=360,
        value=45,
    )

    st.sidebar.caption(
        "If Min > Max, the filter crosses north, e.g. 315° to 45°."
    )
else:
    min_dir = None
    max_dir = None
group_name = st.sidebar.text_input("Group Name", "Custom Selection")
# ==========================================
# MAIN APP AREA & TABS
# ==========================================
st.title("Alaska Point Verification Dashboard")

# Create the two tabs
tab_map, tab_agg, tab_storm = st.tabs([
    "🗺️ Map Explorer",
    "📊 Aggregate Verification",
    "🌪️ Storm Specific Zoom",
])

# ---------------------------------------------------------
# TAB 1: Map Explorer
# ---------------------------------------------------------
with tab_map:
    st.header("Map Explorer")

    if station_meta.empty:
        st.error("Station metadata file not found or empty.")
        st.stop()

    st.markdown("Use metadata filters to choose candidate stations, then compute site-level verification metrics.")

    # Metadata-based filters
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

    selected_zone = None

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
        max_value=5000,
        value=min(300, max(1, len(candidate_stations))),
        step=50,
    )

    candidate_stations = candidate_stations[:max_stations]

    metric_options = [
        "n",
        "bias",
        "mae",
        "rmse",
        "pod",
        "far",
        "csi",
        "event_freq_obs",
        "event_freq_fcst",
        "max_obs",
        "max_fcst",
    ]

    selected_metric = st.selectbox("Map Metric", metric_options, index=2)

    if st.button("Build Station Metric Map", type="primary"):
        with st.spinner("Fetching data and computing station-level verification metrics..."):
            forecast_hours = fcst_hrs_dict.get(model, {}).get(forecast_projection, [])

            modeldf, obdf, error_msg = fetch_data(
                analysis_mode="Aggregate Verification",
                model=model,
                obs=obs,
                start_date=global_start_date,
                end_date=global_end_date,
                station_list=candidate_stations,
                forecast_hours=forecast_hours,
                storm_init_time=None,
                percentile_col_dict=percentile_col_dict,
                percentile=percentile,
                element=element,
                archive_root=archive_root,
            )

            if error_msg:
                st.error(error_msg)
                st.stop()

            merged, raw_obs_col = make_verification_pairs(
                modeldf=modeldf,
                obdf=obdf,
                obs=obs,
                criteria=criteria,
                category_labels_dict=category_labels_dict,
            )

            merged = apply_wind_direction_filter(
                merged,
                use_dir_filter=use_dir_filter,
                min_dir=min_dir,
                max_dir=max_dir,
            )

            station_metrics = compute_station_metrics(
                merged=merged,
                station_meta=station_meta,
                threshold=wind_threshold,
                raw_obs_col=raw_obs_col,
            )

            st.session_state["station_metrics"] = station_metrics
            st.session_state["last_candidate_stations"] = candidate_stations

    if "station_metrics" in st.session_state:
        station_metrics = st.session_state["station_metrics"]

        st.subheader("Station Metric Map")
        plot_station_metric_map(station_metrics, selected_metric)
        show_map_legend(station_metrics, selected_metric)
        st.subheader("Station Metrics Table")

        display_cols = [
            c for c in [
                "station_id",
                "name",
                "wfo_best",
                "station_context",
                "public_zone_id",
                "public_zone_name",
                "coastal_marine_zone_id",
                "coastal_marine_zone_name",
                "n",
                "bias",
                "mae",
                "rmse",
                "pod",
                "far",
                "csi",
                "event_freq_obs",
                "event_freq_fcst",
                "max_obs",
                "max_fcst",
            ]
            if c in station_metrics.columns
        ]

        st.dataframe(
            station_metrics[display_cols].sort_values(selected_metric, ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("##### Select stations for detailed verification")

        selected_stations = st.multiselect(
            "Stations to use in Aggregate Verification",
            options=sorted(station_metrics["station_id"].unique().tolist()),
            default=sorted(station_metrics["station_id"].head(5).tolist()),
        )

        st.session_state["selected_station_list"] = selected_stations

        if selected_stations:
            st.success(
                "Selected stations: " + ", ".join(selected_stations)
            )

# ---------------------------------------------------------
# TAB 2: Aggregate Verification
# ---------------------------------------------------------
with tab_agg:
    st.header("Aggregate Statistics")

    selected_from_map = st.session_state.get("selected_station_list", [])

    default_station_text = ", ".join(selected_from_map) if selected_from_map else "EROWC, LIXA2, RIXA2, NKXA2"

    station_ids_input = st.text_input(
        "Station IDs for Aggregate Verification",
        default_station_text,
    )

    station_list = [s.strip() for s in station_ids_input.split(",") if s.strip()]

    st.caption(f"{len(station_list)} stations selected.")
    
    # Button for Tab 1
    if st.button("Run Aggregate Verification", type="primary"):
        with st.spinner("Fetching and processing aggregate data..."):
            forecast_hours = fcst_hrs_dict.get(model, {}).get(forecast_projection, [])

            modeldf, obdf, error_msg = fetch_data(
                analysis_mode="Aggregate Verification",
                model=model,
                obs=obs,
                start_date=global_start_date,
                end_date=global_end_date,
                station_list=station_list,
                forecast_hours=forecast_hours,
                storm_init_time=None,
                percentile_col_dict=percentile_col_dict,
                percentile=percentile,
                element=element,
                archive_root=archive_root,
            )
                        
            merged, raw_obs_col = make_verification_pairs(
                modeldf=modeldf,
                obdf=obdf,
                obs=obs,
                criteria=criteria,
                category_labels_dict=category_labels_dict,
            )
            merged = apply_wind_direction_filter(
                merged,
                use_dir_filter=use_dir_filter,
                min_dir=min_dir,
                max_dir=max_dir,
            )
            # 4. Draw Plots
            st.subheader("Categorical Verification")
            col1, col2 = st.columns(2)
            with col1:
                fig_bias = plot_forecast_bias_bar_chart(
                    merged,
                    category_labels_dict[criteria][4],
                    category_labels_dict[criteria][3],
                    model,
                    obs,
                    group_name,
                    global_start_date,
                    global_end_date,
                    forecast_projection,
                    category_labels_dict[criteria][1],
                    varname=percentile_col_dict[model][percentile] if model in percentile_col_dict else "wind_speed_kt",
                )
                st.pyplot(fig_bias)
            with col2:
                fig_conf = plot_confusion_matrix(
                    merged,
                    category_labels_dict[criteria][4],
                    category_labels_dict[criteria][3],
                    model,
                    obs,
                    group_name,
                    global_start_date,
                    global_end_date,
                    forecast_projection,
                    category_labels_dict[criteria][1],
                    varname=percentile_col_dict[model][percentile]
                )
                st.pyplot(fig_conf)

            if model in ["nbmqmd", "nbmqmd_exp"]:
                st.markdown("---")
                st.subheader("Probabilistic Verification")
                col3, col4 = st.columns(2)
                merged_rel = merged.rename(columns={"wind_speed_kt":percentile_col_dict[model][percentile]}) if "wind_speed_kt" in merged.columns and percentile_col_dict[model][percentile] not in merged.columns else merged.copy()
                    
                with col3:
                    fig_rel = plot_threshold_reliability(
                        merged_rel,
                        wind_threshold,
                        model,
                        obs,
                        group_name,
                        global_start_date,
                        global_end_date,
                    )
                    st.pyplot(fig_rel)
                with col4:
                    fig_rank = plot_quantile_rank_histogram(
                        merged_rel,
                        model,
                        group_name,
                        global_start_date,
                        global_end_date,
                    )
                    st.pyplot(fig_rank)


# ---------------------------------------------------------
# TAB 3: Storm Specific Zoom
# ---------------------------------------------------------
with tab_storm:
    st.header("Plume Chart Generation")

    s1, s2 = st.columns(2)
    storm_station = s1.text_input("Target Station", "EROWC")
    storm_init_time = s2.text_input("Model Init Time (YYYY-MM-DD HH:MM:SS)", "2026-02-21 00:00:00")

    s3, s4 = st.columns(2)
    storm_start = s3.date_input("Plot Start Date", pd.to_datetime("2026-02-21"))
    storm_end = s4.date_input("Plot End Date", pd.to_datetime("2026-02-24"))

    if st.button("Generate Storm Timeseries", type="primary"):
        with st.spinner(f"Fetching data for {storm_station}..."):
            modeldf, obdf, error_msg = fetch_data(
                analysis_mode="Storm Specific Zoom",
                model=model,
                obs=obs,
                start_date=storm_start,
                end_date=storm_end,
                station_list=[storm_station.strip()],
                forecast_hours=[],
                storm_init_time=storm_init_time,
                percentile_col_dict=percentile_col_dict,
                percentile=percentile,
                element=element,
                archive_root=archive_root,
            )

        if error_msg:
            st.error(error_msg)
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