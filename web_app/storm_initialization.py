"""Storm run controls reflecting the archiver's source-model cycle settings."""
import pandas as pd
import streamlit as st

# alaska_verification archiver_config.NBM_START_HOURS / HERBIE_CYCLES,
# run_model_archiver cycle validation, and nbm_deterministic.source_model.
# Source revision: 11da34de1c4e536a81bcbf173f29517b3d96cd66.
QMD_NBM_ELEMENTS={'maxt','mint','minrh','precip6hr','precip24hr'}


def initialization_hours(model,element):
    if model=='nbm' and element=='minrh':return [0,12]
    source='nbmqmd' if model=='nbm' and element in QMD_NBM_ELEMENTS else model
    if source in ['nbm','nbm_exp']:return [1,7,13,19]
    if source in ['nbmqmd','nbmqmd_exp','hrrr','rrfs','refs']:return [0,6,12,18]
    if source=='urma':return list(range(0,24,3))
    # NDFD references can occur at any hour; do not invent a four-cycle schedule.
    return list(range(24))


def initialization_controls(ui,model,element):
    legacy=st.session_state.get('storm_Model Init Time (YYYY-MM-DD HH:MM:SS)',
        st.session_state.get('_page_settings_storm',{}).get('storm_Model Init Time (YYYY-MM-DD HH:MM:SS)'))
    default=pd.Timestamp('2026-02-21')
    if legacy:
        parsed=pd.to_datetime(legacy,utc=True,errors='coerce')
        if not pd.isna(parsed):default=parsed.tz_convert(None)
    hours=initialization_hours(model,element)
    left,right=ui.columns(2)
    day=left.date_input('Model Init Date',default.date(),key='storm_init_date')
    hour=right.selectbox('Model Init Hour (UTC)',hours,
        index=hours.index(default.hour) if default.hour in hours else 0,
        format_func=lambda value:f'{value:02d}Z',key='storm_init_hour')
    if model=='nbm' and element in QMD_NBM_ELEMENTS:
        st.caption('This NBM element is archived from QMD and uses QMD initialization hours.')
    return pd.Timestamp(day)+pd.Timedelta(hours=hour)
