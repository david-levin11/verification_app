import streamlit as st
import pandas as pd

from config import (
    MODELS,
    OBS_SOURCES,
    PERCENTILES,
    FORECAST_PROJECTION_GROUPS,
    CATEGORY_CONFIG,
    get_available_elements,
    get_available_category_sets,
    get_element_config,
    get_forecast_hours,
    is_probabilistic,
)
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

archive_root = st.sidebar.text_input("Local Archive Root", "../model")

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

group_name = st.sidebar.text_input("Group Name", "Custom Selection")

selected_from_map = st.session_state.get("selected_station_list", [])
default_station_text = ", ".join(selected_from_map) if selected_from_map else "EROWC, LIXA2, RIXA2, NKXA2"

station_ids_input = st.text_input(
    "Station IDs for Aggregate Verification",
    default_station_text,
)

station_list = [s.strip() for s in station_ids_input.split(",") if s.strip()]

st.caption(f"{len(station_list)} stations selected.")

if st.button("Run Aggregate Verification", type="primary"):
    with st.spinner("Fetching and processing aggregate data..."):
        modeldf, obdf, error_msg = fetch_data(
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

        if merged.empty:
            st.warning("No valid model/observation pairs were found.")
            st.stop()

        summary = compute_summary_metrics(
            merged=merged,
            threshold=threshold,
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
        st.dataframe(
            merged[
                [
                    "station_id",
                    "valid_time",
                    "init_time",
                    "forecast_hour",
                    "model_value",
                    "obs_value",
                ]
            ].head(500),
            use_container_width=True,
            hide_index=True,
        )

        category_sets = get_available_category_sets(element)

        if category_sets:
            category_set = st.selectbox("Category Set", category_sets)
            category_cfg = CATEGORY_CONFIG[category_set]

            merged_cat = add_category_columns(
                pairs=merged,
                bins=category_cfg["bins"],
                label_values=list(category_cfg["labels"].keys()),
                model_category_col="model_category",
                obs_category_col="obs_category",
            )

            st.subheader("Categorical Verification")

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