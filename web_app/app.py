import streamlit as st


st.set_page_config(
    page_title="Alaska Point Verification Dashboard",
    page_icon="🌦️",
    layout="wide",
)


st.title("Alaska Point Verification Dashboard")

st.markdown(
    """
    This dashboard supports point-based forecast verification for Alaska model
    archives.

    Use the pages in the sidebar to:

    - explore station-level verification metrics on a map
    - run aggregate verification for selected stations
    - generate storm-specific time series plots
    - compare two models on common forecast/observation cases
    """
)

st.info(
    "Each page has independent settings. Select stations in Map Explorer to use them in "
    "Aggregate Verification or Model Comparison, or enter IDs directly."
)


st.markdown("---")

st.subheader("Current workflow")

st.markdown(
    """
    1. **Map Explorer**
       - Filter stations by metadata such as WFO, station context, and zone.
       - Build station-level verification metrics.
       - Select stations for deeper verification.

    2. **Aggregate Verification**
       - Use selected stations from the map or enter station IDs manually.
       - Compute summary metrics such as bias, MAE, RMSE, POD, FAR, and CSI.
       - View categorical and probabilistic verification where supported.

    3. **Storm Specific Zoom**
       - Generate station-specific time series or plume-style plots.
       - Supports wind, gust, RH, minimum RH, daily temperature extremes, and 6/24-hour precipitation.

    4. **Model Comparison**
       - Choose two models, their shared element, and a forecast reference offset.
       - Score both against the same observation with configurable timing tolerance.
       - Explore lead times, station differences, conditions, and probability diagnostics.
    """
)


st.caption("Each analysis page shows archive date coverage before you run. Tables and technical details are available from Downloads.")
