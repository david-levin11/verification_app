import streamlit as st
import pydeck as pdk


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

    metric_min = map_df[metric].min()
    metric_max = map_df[metric].max()

    if metric_max == metric_min:
        map_df["metric_scaled"] = 0.5
    else:
        map_df["metric_scaled"] = (
            (map_df[metric] - metric_min) / (metric_max - metric_min)
        )

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