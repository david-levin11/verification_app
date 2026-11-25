from pathlib import Path
import sys

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parents[1] / 'web_app'
sys.path.insert(0, str(ROOT))


def test_map_aggregate_and_storm_share_station_aliases(tmp_path):
    target = pd.Timestamp('2026-06-02 06:00')
    init = pd.Timestamp('2026-06-02 01:00')
    earlier_run = pd.Timestamp('2026-06-01 19:00')
    ndbc, bare = 'NDBCRIXA2', 'RIXA2'
    nbm = pd.DataFrame({
        'station_id': [ndbc, bare, bare], 'init_time': [init, init, earlier_run],
        'valid_time': target, 'forecast_hour': [5, 5, 11], 'wind_speed_kt': [10., 99., 15.],
    })
    ndfd = pd.DataFrame({
        'station_id': [bare], 'valid_time': [target], 'forecast_hour': [6],
        'wind_speed_kt': [12.],
    })
    obs = pd.DataFrame({
        'stid': [ndbc], 'valid_time': [target], 'obs_wind_speed_kts': [11.],
    })
    for source, frame in [('nbm', nbm), ('ndfd', ndfd), ('obs', obs)]:
        folder = tmp_path / source / 'wind'
        folder.mkdir(parents=True)
        frame.to_parquet(folder / '2026_06_archive.parquet', index=False)
    metadata = tmp_path / 'stations.csv'
    pd.DataFrame({
        'station_id': [ndbc, bare], 'latitude': [58.177, 58.177], 'longitude': [-135.052, -135.052],
        'mnet_id': [286, 332], 'name': ['Rocky Island', 'Rocky Island'],
    }).to_csv(metadata, index=False)

    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20)
    app.secrets['local'] = {'archive_root': str(tmp_path), 'metadata_path': str(metadata)}
    app.run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.selectbox(key='map_ui_model').set_value('nbm').run()
    app.selectbox(key='map_ui_element').set_value('wind').run()
    app.session_state['selected_station_list'] = [bare, ndbc]
    app.multiselect(key='map_networks').set_value(['332']).run()
    next(button for button in app.button if button.label == 'Build Station Metric Map').click().run()
    assert not app.exception and not app.error
    metrics = app.session_state['station_metrics']
    assert metrics.station_id.tolist() == [ndbc]
    assert metrics.n.tolist() == [2]
    assert app.session_state['selected_station_list'] == [ndbc]
    assert sorted(app.session_state['map_chart_cases'].model_value) == [10., 15.]

    app.switch_page('pages/2_Aggregate_Verification.py').run()
    app.selectbox(key='aggregate_ui_model').set_value('nbm').run()
    app.selectbox(key='aggregate_ui_element').set_value('wind').run()
    app.text_input(key='aggregate_station_ids_input').set_value(f'{bare}, {ndbc}')
    next(button for button in app.button if button.label == 'Run Aggregate Verification').click().run()
    assert not app.exception and not app.error
    paired = app.session_state['aggregate_merged']
    assert paired.station_id.tolist() == [ndbc, ndbc]
    assert sorted(paired.source_station_id) == [ndbc, bare]
    assert paired.obs_station_id.tolist() == [ndbc, ndbc]

    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.selectbox(key='storm_Model').set_value('nbm').run()
    app.selectbox(key='storm_Element').set_value('wind').run()
    app.radio(key='storm_station_scope').set_value('Map Explorer selections').run()
    app.checkbox(key='storm_compare_enabled').set_value(True).run()
    app.selectbox(key='storm_model_b').set_value('ndfd').run()
    app.number_input(key='storm_offset_hours').set_value(-1.)
    app.date_input(key='storm_init_date').set_value(init.date())
    app.selectbox(key='storm_init_hour').set_value(init.hour)
    next(button for button in app.button if button.label == 'Generate Storm Timeseries').click().run()
    assert not app.exception and not app.error
    result = app.session_state['storm_result']
    assert result['cases'].station_id.tolist() == [ndbc]
    assert result['cases'].model_value.tolist() == [10.]
    assert result['cases'].obs_station_id.tolist() == [ndbc]
    assert result['shared'].b_source_station_id.tolist() == [bare]
