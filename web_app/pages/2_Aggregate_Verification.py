import streamlit as st

from sidebar_controls import shared_sidebar_controls

from config import CATEGORY_CONFIG

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

controls = shared_sidebar_controls(show_category_set=True)

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
category_set = controls["category_set"]

# ---------------------------------------------------------------------
# Aggregate-specific controls
# ---------------------------------------------------------------------

group_name = st.sidebar.text_input(
    "Group Name",
    value=st.session_state.get("aggregate_group_name", "Custom Selection"),
    key="aggregate_group_name",
)

selected_from_map = st.session_state.get("selected_station_list", [])
default_station_text = (
    ", ".join(selected_from_map)
    if selected_from_map
    else "EROWC, LIXA2, RIXA2, NKXA2"
)

station_ids_input = st.text_input(
    "Station IDs for Aggregate Verification",
    value=st.session_state.get(
        "aggregate_station_ids_input",
        default_station_text,
    ),
    key="aggregate_station_ids_input",
)

station_list = [s.strip() for s in station_ids_input.split(",") if s.strip()]

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

        if merged.empty:
            st.warning("No valid model/observation pairs were found.")
            st.stop()

        summary = compute_summary_metrics(
            merged=merged,
            threshold=threshold,
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
        "category_set": category_set,
        "group_name": group_name,
        "station_list": station_list,
    }

    if result_context and result_context != current_context:
        st.info(
            "The displayed aggregate verification was computed with previous settings. "
            "Click **Run Aggregate Verification** to refresh with the current sidebar selections."
        )

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

    st.subheader("Paired Data Preview")

    preview_cols = [
        "station_id",
        "valid_time",
        "init_time",
        "forecast_hour",
        "model_value",
        "obs_value",
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

        st.info(
            "The probabilistic plots may need a small update so they use "
            "the element-specific percentile columns from config.py."
        )

        col3, col4 = st.columns(2)

        with col3:
            try:
                fig_rel = plot_threshold_reliability(
                    merged,
                    threshold,
                    model,
                    obs,
                    group_name,
                    start_date,
                    end_date,
                )
                st.pyplot(fig_rel)
            except Exception as e:
                st.warning(f"Could not create reliability plot yet: {e}")

        with col4:
            try:
                fig_rank = plot_quantile_rank_histogram(
                    merged,
                    model,
                    group_name,
                    start_date,
                    end_date,
                )
                st.pyplot(fig_rank)
            except Exception as e:
                st.warning(f"Could not create rank histogram yet: {e}")
else:
    st.info(
        "Choose your settings and click **Run Aggregate Verification**. "
        "Station selections from the Map Explorer page will appear here automatically."
    )