import streamlit as st

from sidebar_controls import shared_sidebar_controls
from page_controls import PageControls
from station_selection import station_ids_input, parse_station_ids

ui = PageControls("aggregate")

from config import CATEGORY_CONFIG, get_element_config, is_probabilistic

from data_loader import fetch_data
from pairing import build_verification_pairs, add_category_columns
from metrics import compute_summary_metrics
from plots import (
    plot_forecast_bias_bar_chart,
    plot_confusion_matrix,
    plot_threshold_reliability,
    plot_quantile_rank_histogram,
)


st.title("Aggregate Verification")

# ---------------------------------------------------------------------
# Shared sidebar controls
# ---------------------------------------------------------------------

controls = shared_sidebar_controls(show_category_set=True, page_key="aggregate")

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
category_set = controls["category_set"]

# ---------------------------------------------------------------------
# Aggregate-specific controls
# ---------------------------------------------------------------------

group_name = ui.sidebar.text_input(
    "Group Name",
    value=st.session_state.get("aggregate_group_name", "Custom Selection"),
    key="aggregate_group_name",
)

station_ids_text = station_ids_input("aggregate", "aggregate_station_ids_input",
    "Station IDs for Aggregate Verification", default="EROWC, LIXA2, RIXA2, NKXA2")
station_list = parse_station_ids(station_ids_text)

st.caption(f"{len(station_list)} stations selected.")

# ---------------------------------------------------------------------
# Fetch and compute
# ---------------------------------------------------------------------

if st.button("Run Aggregate Verification", type="primary"):
    with st.spinner("Fetching and processing aggregate data..."):
        modeldf, obdf, message = fetch_data(
            analysis_mode="Aggregate Verification",
            model=model,
            obs=obs,
            start_date=start_date,
            end_date=end_date,
            station_list=station_list,
            forecast_hours=forecast_hours,
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

        if merged.empty:
            st.warning("No valid model/observation pairs were found.")
            st.stop()

        summary = compute_summary_metrics(
            merged=merged,
            threshold=threshold,
            threshold_operator=threshold_operator,
            element=element,
            probabilistic=model_is_probabilistic,
        )

        st.session_state["aggregate_merged"] = merged
        st.session_state["aggregate_summary"] = summary
        st.session_state["aggregate_context"] = {
            "model": model,
            "element": element,
            "obs": obs,
            "percentile": percentile,
            "forecast_projection": forecast_projection,
            "start_date": start_date,
            "end_date": end_date,
            "threshold": threshold,
            "threshold_operator": threshold_operator,
            "obs_time_tolerance": obs_time_tolerance,
            "category_set": category_set,
            "group_name": group_name,
            "station_list": station_list,
        }

# ---------------------------------------------------------------------
# Display previous/current results
# ---------------------------------------------------------------------

if "aggregate_merged" in st.session_state and "aggregate_summary" in st.session_state:
    merged = st.session_state["aggregate_merged"]
    summary = st.session_state["aggregate_summary"]

    result_context = st.session_state.get("aggregate_context", {})
    current_context = {
        "model": model,
        "element": element,
        "obs": obs,
        "percentile": percentile,
        "forecast_projection": forecast_projection,
        "start_date": start_date,
        "end_date": end_date,
        "threshold": threshold,
            "threshold_operator": threshold_operator,
            "obs_time_tolerance": obs_time_tolerance,
        "category_set": category_set,
        "group_name": group_name,
        "station_list": station_list,
    }

    if result_context and result_context != current_context:
        st.info(
            "The displayed aggregate verification was computed with previous settings. "
            "Click **Run Aggregate Verification** to refresh with the current sidebar selections."
        )

    # Render saved results using the settings that produced them.
    model = result_context.get("model", model)
    element = result_context.get("element", element)
    obs = result_context.get("obs", obs)
    percentile = result_context.get("percentile", percentile)
    category_set = result_context.get("category_set", category_set)
    group_name = result_context.get("group_name", group_name)
    start_date = result_context.get("start_date", start_date)
    end_date = result_context.get("end_date", end_date)
    forecast_projection = result_context.get("forecast_projection", forecast_projection)
    element_cfg = get_element_config(element)
    model_is_probabilistic = is_probabilistic(model, element)

    st.subheader("Summary Metrics")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pairs", f"{summary.get('n', 0):,.0f}")
    c2.metric("Bias", f"{summary.get('bias', float('nan')):.2f}")
    c3.metric("MAE", f"{summary.get('mae', float('nan')):.2f}")
    c4.metric("RMSE", f"{summary.get('rmse', float('nan')):.2f}")

    c5, c6, c7 = st.columns(3)
    c5.metric("POD", f"{summary.get('pod', float('nan')):.2f}")
    c6.metric("FAR", f"{summary.get('far', float('nan')):.2f}")
    c7.metric("CSI", f"{summary.get('csi', float('nan')):.2f}")

    st.caption(f"Event: {element} {result_context.get('threshold_operator', '>=')} "
               f"{result_context.get('threshold', threshold)} {element_cfg['units']}")
    if "brier_score" in summary:
        p1, p2, p3 = st.columns(3)
        p1.metric("Probability cases", f"{summary.get('n_prob', 0):,}")
        p2.metric("Brier score", f"{summary['brier_score']:.4f}")
        p3.metric("Reliability error", f"{summary['reliability_error']:.4f}")
        st.caption("Lower is better for both scores. Reliability error is the weighted "
                   "squared calibration error in 10% probability bins. "
                   "Sparse quantile tails use the nearest available percentile; "
                   "all-equal quantiles are approximated as a point mass.")

    st.subheader("Paired Data Preview")

    preview_cols = [
        "station_id",
        "valid_time",
        "init_time",
        "forecast_hour",
        "model_value",
        "obs_value",
        "obs_valid_time",
        "obs_time_offset_minutes",
        "obs_window_start",
        "obs_window_end",
    ]

    available_preview_cols = [c for c in preview_cols if c in merged.columns]

    st.dataframe(
        merged[available_preview_cols].head(500),
        use_container_width=True,
        hide_index=True,
    )

    # -----------------------------------------------------------------
    # Categorical verification
    # -----------------------------------------------------------------

    if category_set is not None:
        category_cfg = CATEGORY_CONFIG[category_set]

        merged_cat = add_category_columns(
            pairs=merged,
            bins=category_cfg["bins"],
            label_values=list(category_cfg["labels"].keys()),
            model_category_col="model_category",
            obs_category_col="obs_category",
        )

        st.subheader(f"Categorical Verification: {category_set.title()}")

        col1, col2 = st.columns(2)

        with col1:
            fig_bias = plot_forecast_bias_bar_chart(
                merged_cat,
                "obs_category",
                "model_category",
                model,
                obs,
                group_name,
                start_date,
                end_date,
                forecast_projection,
                category_cfg["labels"],
                varname="model_value",
            )
            st.pyplot(fig_bias)

        with col2:
            fig_conf = plot_confusion_matrix(
                merged_cat,
                "obs_category",
                "model_category",
                model,
                obs,
                group_name,
                start_date,
                end_date,
                forecast_projection,
                category_cfg["labels"],
                varname="model_value",
            )
            st.pyplot(fig_conf)

    # -----------------------------------------------------------------
    # Probabilistic verification
    # -----------------------------------------------------------------

    if model_is_probabilistic:
        st.markdown("---")
        st.subheader("Probabilistic Verification")

        st.caption(
            "Reliability and rank histograms use the full set of available forecast "
            "percentile columns for the selected element."
        )

        col3, col4 = st.columns(2)
        with st.expander("Probabilistic plot diagnostics", expanded=False):
            prob_cols = [
                c for c in merged.columns
                if "_p" in c or c.endswith(("_p5", "_p10", "_p25", "_p50", "_p75", "_p90", "_p95"))
            ]

            st.write("Element:", element)
            st.write("Available probabilistic columns:", prob_cols)
            st.write("Merged columns:", merged.columns.tolist())
            
        with col3:
            try:
                fig_rel = plot_threshold_reliability(
                    merged_df=merged,
                    threshold=result_context.get("threshold", threshold),
                    model=model,
                    obs=obs,
                    station_id=group_name,
                    start_date=start_date,
                    end_date=end_date,
                    element=element,
                    obs_col="obs_value",
                    threshold_operator=result_context.get("threshold_operator", threshold_operator),
                )
                st.pyplot(fig_rel)
            except Exception as e:
                st.warning(f"Could not create reliability plot yet: {e}")

        with col4:
            try:
                fig_rank = plot_quantile_rank_histogram(
                    merged_df=merged,
                    model=model,
                    station_id=group_name,
                    start_date=start_date,
                    end_date=end_date,
                    element=element,
                    obs_col="obs_value",
                )
                st.pyplot(fig_rank)
            except Exception as e:
                st.warning(f"Could not create rank histogram yet: {e}")
else:
    st.info(
        "Choose your settings and click **Run Aggregate Verification**. "
        "Station selections from the Map Explorer page will appear here automatically."
    )
