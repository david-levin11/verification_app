"""Small component checks independent of archive startup and verification."""
import streamlit as st
import pandas as pd

st.set_page_config(page_title='Deployment Check', layout='wide')
st.title('Deployment Check')
st.success('The Python page loaded. No archive files were read by this page.')
st.caption(f'Streamlit {st.__version__}. Sample locations: Juneau and Anchorage.')
choice=st.radio('Component to test', ['Text only','Table','Map'])
points=pd.DataFrame({'Station':['PAJN','PANC'],'lat':[58.355,61.174], 'lon':[-134.577,-149.996]})
if choice=='Table':
    st.dataframe(points,hide_index=True)
elif choice=='Map':
    st.map(points,latitude='lat',longitude='lon',zoom=3)
st.write('Python finished rendering the selected test. A component error above indicates a browser or file-delivery failure even with this tiny sample.')
