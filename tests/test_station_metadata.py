"""Station filtering, independent page controls, and readable comparison maps."""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1] / 'web_app'
sys.path.insert(0, str(ROOT))
from station_metadata import filter_station_metadata, normalize_station_metadata, station_context_table
from comparison_plots import station_difference_map


def metadata():
    return pd.DataFrame(dict(station_id=['LOW','HIGH','OTHER','UNKNOWN','BELOW'],
        mnet_id=['332',332.,'96',None,'332'], elevation_ft=['20','500','100',None,'-5'],
        latitude=[58.2,58.3,58.4,58.5,58.6], longitude=[-134.8,-134.9,-135.,-135.1,-135.2]))


def test_network_and_elevation_filters_keep_unknowns_until_requested():
    frame = metadata()
    assert len(filter_station_metadata(frame)) == 5
    assert filter_station_metadata(frame,['332']).station_id.tolist() == ['LOW','HIGH','BELOW']
    assert filter_station_metadata(frame,['332'],0,100).station_id.tolist() == ['LOW']
    assert filter_station_metadata(frame,minimum=0,maximum=100,
        include_unknown_elevation=True).station_id.tolist() == ['LOW','OTHER','UNKNOWN']
    table = station_context_table(frame)
    assert table.sort_values('Elevation (ft)').station_id.tolist()[:2] == ['BELOW','LOW']
    assert table.sort_values('Synoptic Network ID').station_id.iloc[0] == 'OTHER'
    assert len(filter_station_metadata(frame.drop(columns=['mnet_id','elevation_ft']))) == 5
    malformed = frame.copy()
    malformed['elevation_ft'] = ['bad',np.inf,-np.inf,'10','20']
    assert normalize_station_metadata(malformed).elevation_ft.isna().sum() == 3


def test_comparison_map_pixel_sizes_case_counts_and_regional_view():
    meta = normalize_station_metadata(metadata())
    table = pd.DataFrame(dict(station_id=['LOW','HIGH'],metric=['bias']*2,
        n=[10,100],a=[-1.,2.],b=[2.,1.]))
    deck, data = station_difference_map(table,meta,'bias','A','B',minimum_cases=10)
    assert data.advantage.tolist() == [1.,-1.]
    layer = deck.layers[0]
    specification = json.loads(layer.to_json())
    assert specification['radiusUnits'] == 'pixels'
    assert specification['getRadius'] == '@@=point_radius'
    assert data.point_radius.between(4,9).all()
    assert data.point_radius.iloc[1] > data.point_radius.iloc[0]
    assert deck.initial_view_state.zoom > 6
    assert -135 < deck.initial_view_state.longitude < -134
    assert 58 < deck.initial_view_state.latitude < 59
    single, _ = station_difference_map(table,meta,'bias','A','B',minimum_cases=50)
    assert single.initial_view_state.zoom == 9
    assert station_difference_map(table,meta,'bias','A','B',minimum_cases=101)[0] is None


def test_comparison_map_fits_dateline_without_spanning_the_world():
    meta = pd.DataFrame(dict(station_id=['A','B'],latitude=[52.,53.],longitude=[179.,-179.]))
    table = pd.DataFrame(dict(station_id=['A','B'],metric=['mae']*2,n=[20,20],a=[1.,2.],b=[2.,1.]))
    deck, data = station_difference_map(table,meta,'mae','A','B')
    assert abs(deck.initial_view_state.longitude) == 180
    assert deck.initial_view_state.zoom > 5
    assert data.map_longitude.max() - data.map_longitude.min() == 2


def test_pages_apply_filters_independently_and_preserve_them(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import data_loader
    import comparison_loader
    meta = tmp_path/'stations.parquet'
    normalize_station_metadata(metadata()).to_parquet(meta)
    requests = []
    def capture_map(**kwargs):
        requests.append(kwargs['station_list'])
        return pd.DataFrame(), pd.DataFrame(), 'Data Missing: query capture'
    def capture_comparison(*args, **kwargs):
        requests.append(args[7])
        raise ValueError('query capture')
    monkeypatch.setattr(data_loader,'fetch_data',capture_map)
    monkeypatch.setattr(comparison_loader,'load_comparison_data',capture_comparison)
    app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=15).run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.text_input(key='map_metadata_path').set_value(str(meta)).run()
    app.multiselect(key='map_networks').set_value(['332']).run()
    app.checkbox(key='map_filter_elevation').set_value(True).run()
    app.number_input(key='map_elevation_min').set_value(0.)
    app.number_input(key='map_elevation_max').set_value(100.).run()
    next(b for b in app.button if b.label=='Build Station Metric Map').click().run()
    assert not app.exception
    assert requests[-1] == ['LOW']
    app.switch_page('pages/4_Model_Comparison.py').run()
    app.text_input(key='compare_metadata').set_value(str(meta)).run()
    assert app.multiselect(key='compare_networks').value == []
    app.multiselect(key='compare_networks').set_value(['332']).run()
    app.checkbox(key='compare_filter_elevation').set_value(True).run()
    app.number_input(key='compare_elevation_min').set_value(100.)
    app.number_input(key='compare_elevation_max').set_value(1000.).run()
    app.checkbox(key='compare_filtered_stations').set_value(True).run()
    app.button(key='compare_run').click().run()
    assert not app.exception
    assert requests[-1] == ['HIGH']
    app.switch_page('pages/1_Map_Explorer.py').run()
    assert app.multiselect(key='map_networks').value == ['332']
    assert app.number_input(key='map_elevation_max').value == 100.
    assert not app.exception
