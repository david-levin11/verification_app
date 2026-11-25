import streamlit as st


st.set_page_config(
    page_title="Alaska Point Verification Dashboard",
    page_icon="🌦️",
    layout="wide",
)


def home():
    st.title("Alaska Point Verification Dashboard")
    st.markdown(
        """
        Verify archived Alaska forecasts against station observations.

        - **Verification Overview** scores all sites that match your filters.
          Review the all-sites charts and select stations on the map.
        - **Selected-Site Verification** scores the stations you select on the
          map or enter by ID. It picks up the model, element, and dates from
          Verification Overview.
        - **Storm Zoom** plots forecasts and observations for an event at
          individual stations.
        - **Model Comparison** scores two models on common forecast and
          observation cases.
        """
    )
    st.caption("Each analysis page shows archive date coverage before you run. "
               "Tables and technical details are available from Downloads.")


st.navigation([
    st.Page(home, title="Home", default=True),
    st.Page("pages/1_Map_Explorer.py", title="Verification Overview", url_path="Map_Explorer"),
    st.Page("pages/2_Aggregate_Verification.py", title="Selected-Site Verification", url_path="Aggregate_Verification"),
    st.Page("pages/3_Storm_Zoom.py"),
    st.Page("pages/4_Model_Comparison.py"),
]).run()
