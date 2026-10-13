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
    get_forecast_hours_for_projection_range,
    is_probabilistic,
)


# =============================================================================
# Session-state helpers
# =============================================================================

def _safe_index(options, current_value, default_value=None):
    """
    Return a safe index for selectbox/radio widgets.
    """
    if not options:
        return 0

    if default_value is None:
        default_value = options[0]

    if current_value not in options:
        current_value = default_value

    if current_value not in options:
        current_value = options[0]

    return options.index(current_value)


def _init_state(state_key, default_value):
    """
    Initialize durable app state if it does not already exist.
    """
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value


def _sync_from_widget(widget_key, state_key):
    """
    Copy widget value into durable app state.

    This avoids directly assigning to widget-owned keys.
    """
    st.session_state[state_key] = st.session_state[widget_key]


def shared_sidebar_controls(show_category_set=False):
    """
    Shared sidebar controls for the verification pages.

    Returns a dictionary of selected settings.
    """

    # ------------------------------------------------------------------
    # Durable defaults
    # ------------------------------------------------------------------

    _init_state("archive_root", "../model")
    _init_state("model", MODELS[0])
    _init_state("start_date", pd.to_datetime("2025-10-01").date())
    _init_state("end_date", pd.to_datetime("2026-03-17").date())
    _init_state("use_all_forecast_hours", False)

    # ------------------------------------------------------------------
    # Archive root
    # ------------------------------------------------------------------

    archive_root = st.sidebar.text_input(
        "Local Archive Root",
        value=st.session_state["archive_root"],
        key="ui_archive_root",
        on_change=_sync_from_widget,
        args=("ui_archive_root", "archive_root"),
    )

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    current_model = st.session_state.get("model", MODELS[0])
    if current_model not in MODELS:
        current_model = MODELS[0]

    model = st.sidebar.selectbox(
        "Model",
        MODELS,
        index=_safe_index(MODELS, current_model, MODELS[0]),
        key="ui_model",
        on_change=_sync_from_widget,
        args=("ui_model", "model"),
    )

    # Make sure the durable state reflects the value returned on this run.
    st.session_state["model"] = model

    # ------------------------------------------------------------------
    # Element
    # ------------------------------------------------------------------

    available_elements = get_available_elements(model)

    if not available_elements:
        st.sidebar.error(f"No elements are configured for model: {model}")
        st.stop()

    current_element = st.session_state.get("element", available_elements[0])
    if current_element not in available_elements:
        current_element = available_elements[0]

    element = st.sidebar.selectbox(
        "Element",
        available_elements,
        index=_safe_index(available_elements, current_element, available_elements[0]),
        key="ui_element",
        on_change=_sync_from_widget,
        args=("ui_element", "element"),
    )

    st.session_state["element"] = element

    element_cfg = get_element_config(element)

    # ------------------------------------------------------------------
    # Verification source
    # ------------------------------------------------------------------

    available_obs_sources = get_available_obs_sources(element)

    if not available_obs_sources:
        st.sidebar.error(f"No verification sources are configured for element: {element}")
        st.stop()

    current_obs = st.session_state.get("obs", available_obs_sources[0])
    if current_obs not in available_obs_sources:
        current_obs = available_obs_sources[0]

    obs = st.sidebar.selectbox(
        "Verification Source",
        available_obs_sources,
        index=_safe_index(available_obs_sources, current_obs, available_obs_sources[0]),
        key="ui_obs",
        on_change=_sync_from_widget,
        args=("ui_obs", "obs"),
    )

    st.session_state["obs"] = obs

    # ------------------------------------------------------------------
    # Percentile
    # ------------------------------------------------------------------

    model_is_probabilistic = is_probabilistic(model, element)

    if model_is_probabilistic:
        default_percentile = element_cfg["default_percentile"]
        current_percentile = st.session_state.get("percentile", default_percentile)

        if current_percentile not in PERCENTILES:
            current_percentile = default_percentile

        percentile = st.sidebar.selectbox(
            "Verification Percentile",
            PERCENTILES,
            index=_safe_index(PERCENTILES, current_percentile, default_percentile),
            key="ui_percentile",
            on_change=_sync_from_widget,
            args=("ui_percentile", "percentile"),
        )

        st.session_state["percentile"] = percentile

    else:
        percentile = None
        st.sidebar.caption(
            "Deterministic model/element: percentile verification disabled."
        )

    # ------------------------------------------------------------------
    # Forecast projection range
    # ------------------------------------------------------------------

    st.sidebar.markdown("### Forecast Projection")

    use_all_forecast_hours = st.sidebar.checkbox(
        "Use all forecast hours",
        value=st.session_state.get("use_all_forecast_hours", False),
        key="ui_use_all_forecast_hours",
        on_change=_sync_from_widget,
        args=("ui_use_all_forecast_hours", "use_all_forecast_hours"),
    )

    st.session_state["use_all_forecast_hours"] = use_all_forecast_hours

    forecast_projection_options = [
        name for name in FORECAST_PROJECTION_GROUPS.keys()
        if name != "All"
    ]

    if not forecast_projection_options:
        st.sidebar.warning(
            "No forecast projection groups are configured. "
            "All available forecast hours will be used."
        )
        forecast_projection_start = None
        forecast_projection_end = None
        forecast_projection = "All"
        forecast_hours = None

    elif use_all_forecast_hours:
        forecast_projection_start = None
        forecast_projection_end = None
        forecast_projection = "All"

        forecast_hours = get_forecast_hours(
            model=model,
            element=element,
            projection="All",
        )

    else:
        default_start_projection = forecast_projection_options[0]
        default_end_projection = forecast_projection_options[
            min(2, len(forecast_projection_options) - 1)
        ]

        current_start_projection = st.session_state.get(
            "forecast_projection_start",
            default_start_projection,
        )

        current_end_projection = st.session_state.get(
            "forecast_projection_end",
            default_end_projection,
        )

        if current_start_projection not in forecast_projection_options:
            current_start_projection = default_start_projection

        if current_end_projection not in forecast_projection_options:
            current_end_projection = default_end_projection

        forecast_projection_start = st.sidebar.selectbox(
            "Start projection",
            forecast_projection_options,
            index=_safe_index(
                forecast_projection_options,
                current_start_projection,
                default_start_projection,
            ),
            key="ui_forecast_projection_start",
            on_change=_sync_from_widget,
            args=("ui_forecast_projection_start", "forecast_projection_start"),
        )

        st.session_state["forecast_projection_start"] = forecast_projection_start

        forecast_projection_end = st.sidebar.selectbox(
            "End projection",
            forecast_projection_options,
            index=_safe_index(
                forecast_projection_options,
                current_end_projection,
                default_end_projection,
            ),
            key="ui_forecast_projection_end",
            on_change=_sync_from_widget,
            args=("ui_forecast_projection_end", "forecast_projection_end"),
        )

        st.session_state["forecast_projection_end"] = forecast_projection_end

        forecast_hours = get_forecast_hours_for_projection_range(
            model=model,
            element=element,
            start_projection=forecast_projection_start,
            end_projection=forecast_projection_end,
        )

        forecast_projection = (
            f"{forecast_projection_start} through {forecast_projection_end}"
        )

    if forecast_hours is None:
        pass

    elif not forecast_hours:
        st.sidebar.warning(
            "No forecast hours are configured for this model/element/projection range. "
            "All available forecast hours will be used."
        )
        forecast_hours = None

    else:
        st.sidebar.caption(
            f"{forecast_projection}: {len(forecast_hours)} forecast hours"
        )

    # ------------------------------------------------------------------
    # Date range
    # ------------------------------------------------------------------

    date_col1, date_col2 = st.sidebar.columns(2)

    start_date = date_col1.date_input(
        "Start Date",
        value=st.session_state.get(
            "start_date",
            pd.to_datetime("2025-10-01").date(),
        ),
        key="ui_start_date",
        on_change=_sync_from_widget,
        args=("ui_start_date", "start_date"),
    )

    st.session_state["start_date"] = start_date

    end_date = date_col2.date_input(
        "End Date",
        value=st.session_state.get(
            "end_date",
            pd.to_datetime("2026-03-17").date(),
        ),
        key="ui_end_date",
        on_change=_sync_from_widget,
        args=("ui_end_date", "end_date"),
    )

    st.session_state["end_date"] = end_date

    # ------------------------------------------------------------------
    # Threshold
    # ------------------------------------------------------------------

    threshold_options = element_cfg["thresholds"]
    default_threshold = element_cfg["default_threshold"]

    current_threshold = st.session_state.get("threshold", default_threshold)

    if current_threshold not in threshold_options:
        current_threshold = default_threshold

    threshold = st.sidebar.selectbox(
        f"Threshold ({element_cfg['units']})",
        threshold_options,
        index=_safe_index(threshold_options, current_threshold, default_threshold),
        key="ui_threshold",
        on_change=_sync_from_widget,
        args=("ui_threshold", "threshold"),
    )

    st.session_state["threshold"] = threshold

    operator_options = [">=", ">", "<=", "<"]
    operator_key = f"threshold_operator_{element}"
    default_operator = element_cfg.get("threshold_operator", ">=")
    threshold_operator = st.sidebar.selectbox(
        "Event definition",
        operator_options,
        index=_safe_index(operator_options, st.session_state.get(operator_key), default_operator),
        key=f"ui_{operator_key}",
        on_change=_sync_from_widget,
        args=(f"ui_{operator_key}", operator_key),
        help="Applied consistently to forecast values, observations, and probabilities.",
    )
    st.session_state[operator_key] = threshold_operator
    tolerance_minutes = st.sidebar.number_input(
        "Observation time tolerance (minutes)", min_value=0, max_value=180,
        value=int(st.session_state.get("obs_tolerance_minutes", 60)), step=5,
        key="ui_obs_tolerance_minutes", on_change=_sync_from_widget,
        args=("ui_obs_tolerance_minutes", "obs_tolerance_minutes"),
        help="Nearest report to the forecast valid time or accumulation endpoint; 0 requires exact matching.",
    )
    st.session_state["obs_tolerance_minutes"] = tolerance_minutes
    obs_time_tolerance = f"{tolerance_minutes}min"
    st.sidebar.caption("Daily temperatures use their configured date; accumulation durations must agree.")

    # ------------------------------------------------------------------
    # Category set
    # ------------------------------------------------------------------

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

            category_set = st.sidebar.selectbox(
                "Category Set",
                category_sets,
                index=_safe_index(
                    category_sets,
                    current_category_set,
                    category_sets[0],
                ),
                key="ui_category_set",
                on_change=_sync_from_widget,
                args=("ui_category_set", "category_set"),
            )

            st.session_state["category_set"] = category_set

    return {
        "archive_root": archive_root,
        "model": model,
        "element": element,
        "obs": obs,
        "element_cfg": element_cfg,
        "model_is_probabilistic": model_is_probabilistic,
        "percentile": percentile,
        "forecast_projection": forecast_projection,
        "forecast_projection_start": forecast_projection_start,
        "forecast_projection_end": forecast_projection_end,
        "forecast_hours": forecast_hours,
        "start_date": start_date,
        "end_date": end_date,
        "threshold": threshold,
        "threshold_operator": threshold_operator,
        "obs_time_tolerance": obs_time_tolerance,
        "category_set": category_set,
    }
