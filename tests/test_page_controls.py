"""Navigation, explicit imports, and map event regressions."""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).parents[1] / 'web_app'
sys.path.insert(0, str(ROOT))


def test_map_click_toggle_hidden_selection_and_clear(monkeypatch):
    import station_selection as selection
    state = {'selected_station_list': ['HIDDEN']}
    monkeypatch.setattr(selection.st, 'session_state', state)
    def click(ids):
        state['chart'] = {'selection': {'objects': {'metadata-stations': [
            {'station_id': sid} for sid in ids]}}}
        selection.update_map_selection('chart', 'metadata-stations')
    click(['PAJN'])
    assert state['selected_station_list'] == ['HIDDEN', 'PAJN']
    click(['PAJN', 'PANC'])
    assert state['selected_station_list'] == ['HIDDEN', 'PAJN', 'PANC']
    click(['PANC'])
    assert state['selected_station_list'] == ['HIDDEN', 'PANC']
    selection.remove_station('PANC')
    assert state['selected_station_list'] == ['HIDDEN']
    selection.remove_station()
    assert state['selected_station_list'] == []
    assert state['_station_selection_epoch'] == 2
    assert selection.parse_station_ids('pajn, PANC,PAJN\n  ') == ['PAJN', 'PANC']


def test_pages_keep_settings_and_import_stations_explicitly(tmp_path):
    from streamlit.testing.v1 import AppTest
    meta = tmp_path / 'stations.parquet'
    pd.DataFrame({'station_id':['PAJN', 'PANC'], 'latitude':[58.3,61.2],
        'longitude':[-134.5,-149.9], 'name':['Juneau','Anchorage'],
        'wfo_best':['AJK','AFC']}).to_parquet(meta)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.text_input(key='map_metadata_path').set_value(str(meta)).run()
    assert not app.exception
    assert len(app.get('deck_gl_json_chart')) == 1  # no archive calculation required
    app.selectbox(key='map_ui_model').set_value('nbmqmd').run()
    app.selectbox(key='map_ui_element').set_value('precip24hr').run()
    # A map event callback owns the shared list; destination pages never auto-copy it.
    app.session_state['selected_station_list'] = ['PAJN', 'PANC']
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    assert not app.exception
    assert app.selectbox(key='aggregate_ui_element').value == 'wind'
    app.text_input(key='aggregate_station_ids_input').set_value('CUSTOM').run()
    app.selectbox(key='aggregate_ui_model').set_value('nbmqmd_exp').run()
    app.selectbox(key='aggregate_ui_element').set_value('mint').run()
    assert not app.exception
    assert app.text_input(key='aggregate_station_ids_input').value == 'CUSTOM'
    app.button(key='aggregate_import_map').click().run()
    assert app.text_input(key='aggregate_station_ids_input').value == 'PAJN, PANC'
    app.switch_page('pages/4_Model_Comparison.py').run()
    app.text_input(key='compare_metadata').set_value(str(meta)).run()
    app.checkbox(key='compare_use_offset').set_value(True).run()
    app.number_input(key='compare_offset').set_value(-12.)
    app.checkbox(key='compare_filtered_stations').set_value(True).run()
    app.button(key='compare_import_map').click().run()
    assert not app.exception
    assert app.text_input(key='compare_stations').value == 'PAJN, PANC'
    assert app.checkbox(key='compare_filtered_stations').value is False
    app.text_input(key='compare_stations').set_value('MANUAL').run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    assert not app.exception
    assert app.selectbox(key='map_ui_model').value == 'nbmqmd'
    assert app.selectbox(key='map_ui_element').value == 'precip24hr'
    app.button(key='remove_map_PAJN').click().run()
    assert app.session_state['selected_station_list'] == ['PANC']
    app.selectbox(key='map_wfo').set_value('AJK').run()
    assert app.session_state['selected_station_list'] == ['PANC']  # hidden selection retained
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    assert app.selectbox(key='aggregate_ui_model').value == 'nbmqmd_exp'
    assert app.selectbox(key='aggregate_ui_element').value == 'mint'
    assert app.text_input(key='aggregate_station_ids_input').value == 'PAJN, PANC'
    # Unsupported elements and their dependent thresholds reset safely.
    app.selectbox(key='aggregate_ui_model').set_value('hrrr').run()
    assert not app.exception
    app.switch_page('pages/4_Model_Comparison.py').run()
    assert app.text_input(key='compare_stations').value == 'MANUAL'
    assert app.number_input(key='compare_offset').value == -12.
    app.switch_page('pages/3_Storm_Zoom.py').run()
    assert not app.exception
    app.text_input(key='storm_Target Station').set_value('PANC').run()
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    app.switch_page('pages/3_Storm_Zoom.py').run()
    assert app.text_input(key='storm_Target Station').value == 'PANC'
    assert not app.exception
