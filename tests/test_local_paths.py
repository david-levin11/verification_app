"""Administrator paths apply consistently and cannot be changed by browser widgets."""
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from streamlit.testing.v1 import AppTest


def test_configured_paths_ignore_browser_state(tmp_path):
    script='''
import streamlit as st
from archive_paths import configured_paths
st.json(configured_paths())
'''
    app=AppTest.from_string(script)
    paths={'archive_root':str(tmp_path/'model'),'refs_root':str(tmp_path/'separate/refs'),
           'metadata_path':str(tmp_path/'stations.parquet')}
    app.secrets['local']=paths
    app.session_state['map_ui_archive_root']='/untrusted/browser/path'
    app.run()
    import json
    assert not app.exception
    assert json.loads(app.json[0].value)==paths


def test_no_config_has_repository_relative_defaults(monkeypatch):
    import archive_paths
    monkeypatch.setattr(archive_paths.st,'secrets',{})
    result=archive_paths.configured_paths()
    assert result['archive_root']==str(archive_paths.REPOSITORY_ROOT/'model')
    assert result['refs_root']==str(archive_paths.REPOSITORY_ROOT/'derived/refs')
    assert result['metadata_path']==str(archive_paths.REPOSITORY_ROOT/'metadata/ak_station_metadata.parquet')


def test_all_pages_have_no_path_inputs(tmp_path):
    meta=tmp_path/'stations.parquet'
    pd.DataFrame({'station_id':['PAJN'],'latitude':[58.3],'longitude':[-134.5]}).to_parquet(meta)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'))
    app.secrets['local']={'archive_root':str(tmp_path/'model'),'refs_root':str(tmp_path/'derived/refs'),
                         'metadata_path':str(meta)}
    app.run()
    for page in ['1_Map_Explorer','2_Aggregate_Verification','3_Storm_Zoom','4_Model_Comparison']:
        app.switch_page(f'pages/{page}.py').run()
        assert not app.exception
        models={'1_Map_Explorer':'map_ui_model','2_Aggregate_Verification':'aggregate_ui_model',
                '3_Storm_Zoom':'storm_Model','4_Model_Comparison':'compare_model_a'}
        app.selectbox(key=models[page]).set_value('refs').run()
        assert not app.exception
        assert not any('Root' in x.label or 'Metadata Path' in x.label for x in app.text_input)
