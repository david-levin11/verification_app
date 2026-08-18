import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st


METRIC_COLOR_CONFIG = {
    # Error / continuous metrics
    "bias": {
        "scale": "diverging_zero",
        "label": "Bias",
        "low_label": "Negative",
        "mid_label": "0",
        "high_label": "Positive",
    },
    "mae": {
        "scale": "sequential",
        "label": "MAE",
        "low_label": "Lower",
        "high_label": "Higher",
    },
    "rmse": {
        "scale": "sequential",
        "label": "RMSE",
        "low_label": "Lower",
        "high_label": "Higher",
    },

    # Categorical verification metrics
    "pod": {
        "scale": "fixed_0_1",
        "label": "POD",
        "low_label": "0",
        "high_label": "1",
    },
    "far": {
        "scale": "fixed_0_1_reversed",
        "label": "FAR",
        "low_label": "0",
        "high_label": "1",
    },
    "csi": {
        "scale": "fixed_0_1",
        "label": "CSI",
        "low_label": "0",
        "high_label": "1",
    },

    # Event frequencies
    "event_freq_obs": {
        "scale": "fixed_0_1",
        "label": "Observed Event Frequency",
        "low_label": "0",
        "high_label": "1",
    },
    "event_freq_fcst": {
        "scale": "fixed_0_1",
        "label": "Forecast Event Frequency",
        "low_label": "0",
        "high_label": "1",
    },

    # Counts
    "n": {
        "scale": "sequential",
        "label": "Sample Size",
        "low_label": "Fewer",
        "high_label": "More",
    },
}


def _normalize(value, vmin, vmax):
    """Normalize value to 0-1."""
    if pd.isna(value):
        return np.nan

    if vmax == vmin:
        return 0.5

    return float(np.clip((value - vmin) / (vmax - vmin), 0, 1))


def _interp_color(c1, c2, t):
    """Linearly interpolate between two RGB colors."""
    t = float(np.clip(t, 0, 1))
    return [
        int(c1[i] + (c2[i] - c1[i]) * t)
        for i in range(3)
    ]


def _sequential_color(t):
    """
    Light-to-dark sequential scale.
    Low values are light, high values are dark.
    """
    low = [229, 245, 249]
    high = [44, 127, 184]
    return _interp_color(low, high, t) + [190]


def _diverging_color(t):
    """
    Blue-white-red diverging scale.
    t=0 is negative extreme, t=0.5 is near zero, t=1 is positive extreme.
    """
    blue = [49, 130, 189]
    white = [245, 245, 245]
    red = [203, 24, 29]

    if t <= 0.5:
        return _interp_color(blue, white, t / 0.5) + [210]
    else:
        return _interp_color(white, red, (t - 0.5) / 0.5) + [210]


def _metric_bounds(df, metric):
    """
    Return vmin/vmax based on the metric type.
    """
    cfg = METRIC_COLOR_CONFIG.get(metric, {"scale": "sequential"})
    scale = cfg["scale"]

    values = pd.to_numeric(df[metric], errors="coerce").replace([np.inf, -np.inf], np.nan)

    if scale == "fixed_0_1" or scale == "fixed_0_1_reversed":
        return 0.0, 1.0

    if scale == "diverging_zero":
        max_abs = values.abs().quantile(0.95)

        if pd.isna(max_abs) or max_abs == 0:
            max_abs = values.abs().max()

        if pd.isna(max_abs) or max_abs == 0:
            max_abs = 1.0

        return -float(max_abs), float(max_abs)

    # Sequential fallback.
    vmin = values.quantile(0.05)
    vmax = values.quantile(0.95)

    if pd.isna(vmin) or pd.isna(vmax) or vmin == vmax:
        vmin = values.min()
        vmax = values.max()

    if pd.isna(vmin) or pd.isna(vmax) or vmin == vmax:
        vmin, vmax = 0.0, 1.0

    return float(vmin), float(vmax)


def add_map_style_columns(df, metric):
    """
    Add color and radius columns used by the pydeck layer.
    """
    out = df.copy()

    cfg = METRIC_COLOR_CONFIG.get(metric, {"scale": "sequential"})
    scale = cfg["scale"]

    vmin, vmax = _metric_bounds(out, metric)

    colors = []

    for value in pd.to_numeric(out[metric], errors="coerce"):
        if pd.isna(value):
            colors.append([160, 160, 160, 80])
            continue

        if scale == "diverging_zero":
            t = _normalize(value, vmin, vmax)
            colors.append(_diverging_color(t))

        elif scale == "fixed_0_1":
            t = _normalize(value, 0.0, 1.0)
            colors.append(_sequential_color(t))

        elif scale == "fixed_0_1_reversed":
            # Useful for FAR where lower is better.
            t = 1.0 - _normalize(value, 0.0, 1.0)
            colors.append(_sequential_color(t))

        else:
            t = _normalize(value, vmin, vmax)
            colors.append(_sequential_color(t))

    out["fill_color"] = colors

    # Pixel radius. This keeps points from growing huge when zooming in.
    # You can tune these values.
    if "n" in out.columns:
        n_values = pd.to_numeric(out["n"], errors="coerce").fillna(0)
        n_norm = n_values.rank(pct=True).fillna(0.5)
        out["point_radius"] = 4 + (n_norm * 5)
    else:
        out["point_radius"] = 6

    out["metric_value"] = pd.to_numeric(out[metric], errors="coerce")

    return out, vmin, vmax


def show_map_legend(station_metrics, selected_metric):
    """
    Display a simple metric-aware map legend.
    """

    if station_metrics.empty or selected_metric not in station_metrics.columns:
        return

    cfg = METRIC_COLOR_CONFIG.get(
        selected_metric,
        {
            "scale": "sequential",
            "label": selected_metric,
            "low_label": "Lower",
            "high_label": "Higher",
        },
    )

    vmin, vmax = _metric_bounds(station_metrics, selected_metric)

    scale = cfg["scale"]
    label = cfg.get("label", selected_metric)

    if scale == "diverging_zero":
        st.markdown(
            f"""
            <div style="margin-bottom: 0.5rem;">
              <div style="font-weight: 600;">{label}</div>
              <div style="
                  height: 14px;
                  border-radius: 999px;
                  background: linear-gradient(to right,
                      rgb(49,130,189),
                      rgb(245,245,245),
                      rgb(203,24,29)
                  );
                  border: 1px solid rgba(0,0,0,0.2);
              "></div>
              <div style="display: flex; justify-content: space-between; font-size: 0.85rem;">
                <span>{vmin:.2f}</span>
                <span>0</span>
                <span>{vmax:.2f}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif scale == "fixed_0_1_reversed":
        st.markdown(
            f"""
            <div style="margin-bottom: 0.5rem;">
              <div style="font-weight: 600;">{label}</div>
              <div style="
                  height: 14px;
                  border-radius: 999px;
                  background: linear-gradient(to right,
                      rgb(44,127,184),
                      rgb(229,245,249)
                  );
                  border: 1px solid rgba(0,0,0,0.2);
              "></div>
              <div style="display: flex; justify-content: space-between; font-size: 0.85rem;">
                <span>0 better</span>
                <span>1 worse</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif scale == "fixed_0_1":
        st.markdown(
            f"""
            <div style="margin-bottom: 0.5rem;">
              <div style="font-weight: 600;">{label}</div>
              <div style="
                  height: 14px;
                  border-radius: 999px;
                  background: linear-gradient(to right,
                      rgb(229,245,249),
                      rgb(44,127,184)
                  );
                  border: 1px solid rgba(0,0,0,0.2);
              "></div>
              <div style="display: flex; justify-content: space-between; font-size: 0.85rem;">
                <span>0</span>
                <span>1</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            f"""
            <div style="margin-bottom: 0.5rem;">
              <div style="font-weight: 600;">{label}</div>
              <div style="
                  height: 14px;
                  border-radius: 999px;
                  background: linear-gradient(to right,
                      rgb(229,245,249),
                      rgb(44,127,184)
                  );
                  border: 1px solid rgba(0,0,0,0.2);
              "></div>
              <div style="display: flex; justify-content: space-between; font-size: 0.85rem;">
                <span>{vmin:.2f}</span>
                <span>{vmax:.2f}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

def plot_station_metric_map(station_metrics, selected_metric):
    """
    Plot station-level metrics using metric-aware colors and pixel-sized points.
    """

    if station_metrics.empty:
        st.warning("No station metrics available for mapping.")
        return

    required_cols = ["latitude", "longitude", selected_metric]

    missing_cols = [
        col for col in required_cols
        if col not in station_metrics.columns
    ]

    if missing_cols:
        st.warning(f"Cannot plot map. Missing columns: {missing_cols}")
        return

    map_df = station_metrics.dropna(
        subset=["latitude", "longitude", selected_metric]
    ).copy()

    if map_df.empty:
        st.warning("No stations with valid latitude, longitude, and selected metric.")
        return

    map_df, vmin, vmax = add_map_style_columns(map_df, selected_metric)

    center_lat = float(map_df["latitude"].mean())
    center_lon = float(map_df["longitude"].mean())

    tooltip = {
        "html": """
        <b>{station_id}</b><br/>
        Metric value: {metric_value}<br/>
        N: {n}<br/>
        Bias: {bias}<br/>
        MAE: {mae}<br/>
        RMSE: {rmse}<br/>
        POD: {pod}<br/>
        FAR: {far}<br/>
        CSI: {csi}
        """,
        "style": {
            "backgroundColor": "white",
            "color": "black",
        },
    }

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[longitude, latitude]",
        get_fill_color="fill_color",
        get_radius="point_radius",

        # Key change:
        # Pixel units prevent dots from expanding dramatically as you zoom in.
        radius_units="pixels",
        radius_min_pixels=3,
        radius_max_pixels=10,

        pickable=True,
        stroked=True,
        get_line_color=[40, 40, 40, 180],
        line_width_min_pixels=1,
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=4,
        pitch=0,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    )

    st.pydeck_chart(deck)