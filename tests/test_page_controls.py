"""Navigation, automatic station propagation, and map event regressions."""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).parents[1] / 'web_app'
sys.path.insert(0, str(ROOT))


def test_map_queries_every_filtered_station_without_a_cap(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import data_loader
    stations = [f'S{i:04d}' for i in range(451)]
    meta = tmp_path / 'stations.parquet'
    pd.DataFrame(dict(station_id=stations, latitude=[60.]*451,
        longitude=[-150.]*451, wfo_best=['AJK']*350+['AFC']*101)).to_parquet(meta)
    requests = []
    def capture_query(**kwargs):
        requests.append(kwargs['station_list'])
        return pd.DataFrame(), pd.DataFrame(), 'Data Missing: synthetic query capture'
    monkeypatch.setattr(data_loader, 'fetch_data', capture_query)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=15).run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.text_input(key='map_metadata_path').set_value(str(meta)).run()
    assert not app.exception
    assert not any(n.label == 'Maximum stations to query' for n in app.number_input)
    next(b for b in app.button if b.label == 'Build Station Metric Map').click().run()
    assert not app.exception
    assert requests[-1] == stations
    app.selectbox(key='map_wfo').set_value('AJK').run()
    next(b for b in app.button if b.label == 'Build Station Metric Map').click().run()
    assert not app.exception
    assert requests[-1] == stations[:350]


def test_map_events_viewport_remove_clear_and_deduplication(monkeypatch):
    import station_selection as selection
    from station_map import apply_map_event
    state = {}
    monkeypatch.setattr(selection.st, 'session_state', state)
    view = dict(latitude=58.3, longitude=-134.5, zoom=9.5, pitch=0, bearing=0)
    def event(number, ids):
        apply_map_event(dict(event_id=str(number), station_ids=ids, view_state=view))
    event(1, ['PAJN', 'HIDDEN'])
    assert state['selected_station_list'] == ['HIDDEN', 'PAJN']
    assert state['_station_map_view'] == view
    event(2, ['PANC', 'PAJN', 'HIDDEN'])
    assert state['selected_station_list'] == ['HIDDEN', 'PAJN', 'PANC']
    event(3, ['PANC', 'HIDDEN'])
    assert state['selected_station_list'] == ['HIDDEN', 'PANC']
    revision = state['_map_selection_revision']
    selection.remove_station('PANC')
    assert state['selected_station_list'] == ['HIDDEN']
    assert state['_map_selection_revision'] == revision + 1
    event(3, ['PANC', 'HIDDEN'])  # An old component return must not undo removal.
    assert state['selected_station_list'] == ['HIDDEN']
    selection.remove_station()
    assert state['selected_station_list'] == []
    assert state['_station_map_view'] == view
    assert selection.parse_station_ids('pajn, PANC,PAJN\n  ') == ['PAJN', 'PANC']


def test_pages_keep_settings_and_receive_new_map_selection_automatically(tmp_path):
    from streamlit.testing.v1 import AppTest
    meta = tmp_path / 'stations.parquet'
    pd.DataFrame({'station_id':['PAJN', 'PANC'], 'latitude':[58.3,61.2],
        'longitude':[-134.5,-149.9], 'name':['Juneau','Anchorage'],
        'wfo_best':['AJK','AFC']}).to_parquet(meta)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=15).run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.text_input(key='map_metadata_path').set_value(str(meta)).run()
    assert not app.exception
    assert len(app.get('component_instance')) == 0  # only a generated metric map can select stations
    app.selectbox(key='map_ui_model').set_value('nbmqmd').run()
    app.selectbox(key='map_ui_element').set_value('precip24hr').run()
    # The map component publishes shared selection and a revision.
    app.session_state['selected_station_list'] = ['PAJN', 'PANC']
    app.session_state['_map_selection_revision'] = 1
    # Show an existing generated metric map while testing navigation and removal.
    metrics = pd.read_parquet(meta)
    metrics['n'] = 10
    metrics['mae'] = 1.
    metrics['bias'] = 0.
    app.session_state['station_metrics'] = metrics
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    assert not app.exception
    assert app.selectbox(key='aggregate_ui_element').value == 'wind'
    assert app.text_input(key='aggregate_station_ids_input').value == 'PAJN, PANC'
    assert not any(b.label == 'Use selected map stations' for b in app.button)
    app.text_input(key='aggregate_station_ids_input').set_value('CUSTOM').run()
    app.selectbox(key='aggregate_ui_model').set_value('nbmqmd_exp').run()
    app.selectbox(key='aggregate_ui_element').set_value('mint').run()
    assert not app.exception
    assert app.text_input(key='aggregate_station_ids_input').value == 'CUSTOM'

    app.switch_page('pages/4_Model_Comparison.py').run()
    app.text_input(key='compare_metadata').set_value(str(meta)).run()
    app.checkbox(key='compare_use_offset').set_value(True).run()
    app.number_input(key='compare_offset').set_value(-12.)
    assert not any(b.label == 'Use selected map stations' for b in app.button)
    assert not app.exception
    assert app.text_input(key='compare_stations').value == 'PAJN, PANC'
    assert app.checkbox(key='compare_filtered_stations').value is False
    app.text_input(key='compare_stations').set_value('MANUAL').run()
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    assert app.text_input(key='aggregate_station_ids_input').value == 'CUSTOM'
    app.switch_page('pages/4_Model_Comparison.py').run()
    assert app.text_input(key='compare_stations').value == 'MANUAL'
    app.checkbox(key='compare_filtered_stations').set_value(True).run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    assert not app.exception
    assert app.selectbox(key='map_ui_model').value == 'nbmqmd'
    assert app.selectbox(key='map_ui_element').value == 'precip24hr'
    assert len(app.get('component_instance')) == 1
    app.button(key='remove_map_PAJN').click().run()
    assert app.session_state['selected_station_list'] == ['PANC']
    app.selectbox(key='map_wfo').set_value('AJK').run()
    assert app.session_state['selected_station_list'] == ['PANC']  # hidden selection retained
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    assert app.selectbox(key='aggregate_ui_model').value == 'nbmqmd_exp'
    assert app.selectbox(key='aggregate_ui_element').value == 'mint'
    assert app.text_input(key='aggregate_station_ids_input').value == 'PANC'
    # Unsupported elements and their dependent thresholds reset safely.
    app.selectbox(key='aggregate_ui_model').set_value('hrrr').run()
    assert not app.exception
    app.switch_page('pages/4_Model_Comparison.py').run()
    assert app.text_input(key='compare_stations').value == 'PANC'
    assert app.checkbox(key='compare_filtered_stations').value is False
    assert app.number_input(key='compare_offset').value == -12.
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.button(key='clear_map_stations').click().run()
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    assert app.text_input(key='aggregate_station_ids_input').value == ''
    app.switch_page('pages/4_Model_Comparison.py').run()
    assert app.text_input(key='compare_stations').value == ''
    app.switch_page('pages/3_Storm_Zoom.py').run()
    assert not app.exception
    app.radio(key='storm_station_scope').set_value('Map Explorer selections').run()
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    app.switch_page('pages/3_Storm_Zoom.py').run()
    assert app.radio(key='storm_station_scope').value == 'Map Explorer selections'
    assert not app.exception
