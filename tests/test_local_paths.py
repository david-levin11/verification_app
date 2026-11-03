"""Machine defaults populate all page path widgets without replacing user edits."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from streamlit.testing.v1 import AppTest

SCRIPT='''
from page_controls import PageControls
for page,key in [('map','ui_archive_root'),('aggregate','ui_archive_root'),('storm','Local Archive Root'),('compare','compare_archive_root')]:
    ui=PageControls(page)
    ui.text_input('Archive', '../model',key=key)
    ui.text_input('REFS', '../derived/refs',key='refs_root')
for page,key in [('map','metadata_path'),('storm','storm_metadata'),('compare','compare_metadata')]:
    PageControls(page).text_input('Metadata','../metadata/ak_station_metadata.parquet',key=key)
'''

def test_machine_paths_and_session_override():
    app=AppTest.from_string(SCRIPT)
    app.secrets['local']={'archive_root':'G:/shared/model','refs_root':'G:/other/derived/refs','metadata_path':'G:/shared/stations.parquet'}
    app.run()
    assert not app.exception
    for prefix in ['map','aggregate','storm','compare']:
        assert app.text_input(key=f'{prefix}_refs_root').value=='G:/other/derived/refs'
    for key in ['map_ui_archive_root','aggregate_ui_archive_root','storm_Local Archive Root','compare_archive_root']:
        assert app.text_input(key=key).value=='G:/shared/model'
    for key in ['map_metadata_path','storm_metadata','compare_metadata']:
        assert app.text_input(key=key).value=='G:/shared/stations.parquet'
    app.text_input(key='map_ui_archive_root').set_value('D:/alternate/model').run()
    assert app.text_input(key='map_ui_archive_root').value=='D:/alternate/model'
    assert app.text_input(key='compare_archive_root').value=='G:/shared/model'

def test_unconfigured_paths_keep_existing_defaults():
    app=AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert app.text_input(key='map_ui_archive_root').value=='../model'
    assert app.text_input(key='storm_refs_root').value=='../derived/refs'
