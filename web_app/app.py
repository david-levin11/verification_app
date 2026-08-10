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
    """
)

st.info(
    "Recommended workflow: start with Map Explorer, select stations, then move "
    "to Aggregate Verification."
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
       - Currently optimized for wind and gust workflows.
    """
)


st.subheader("Archive structure")

st.code(
    """
verification_app/
├── model/
│   ├── nbm/
│   ├── nbmqmd/
│   ├── nbmqmd_exp/
│   ├── hrrr/
│   ├── ndfd/
│   └── urma/
└── web_app/
    ├── app.py
    ├── config.py
    ├── data_loader.py
    ├── pairing.py
    ├── metrics.py
    ├── maps.py
    ├── plots.py
    └── pages/
        ├── 1_Map_Explorer.py
        ├── 2_Aggregate_Verification.py
        └── 3_Storm_Zoom.py
    """,
    language="text",
)


st.subheader("Standard paired verification format")

st.markdown(
    """
    The refactored workflow is built around a common paired dataframe with these
    core columns:
    """
)

st.code(
    """
station_id
valid_time
init_time
forecast_hour
model_value
obs_value
    """,
    language="text",
)


st.caption(
    "The app is being refactored toward a model/element-aware verification "
    "workflow using config.py, pairing.py, metrics.py, maps.py, and plots.py."
)