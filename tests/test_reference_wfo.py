from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
ROOT=Path(__file__).parents[1]/'web_app'
sys.path.insert(0,str(ROOT))
from station_metadata import normalize_station_metadata
from reference_guide import cycle_matches,earlier_offsets,typical_hours


def test_coastal_offshore_and_synoptic_wfo_fallbacks_preserve_existing():
    frame=pd.DataFrame(dict(station_id=['EXISTING','PUBLIC','COAST','OFFSHORE','SYNOPTIC','UNKNOWN'],
        wfo_best=['AFG','',None,'unknown','nan',None],
        public_zone_wfo=['AJK',' ajk ',None,None,None,None],
        coastal_marine_zone_wfo=['AJK',None,'AJK',None,None,None],
        offshore_zone_wfo=[None,None,None,'AFC',None,None],
        cwa_synoptic=[None,None,None,None,'AFC',None]))
    result=normalize_station_metadata(frame)
    assert result.wfo_best.iloc[:5].tolist()==['AFG','AJK','AJK','AFC','AFC']
    assert pd.isna(result.wfo_best.iloc[5])
    assert result.wfo_assignment_source.iloc[:5].tolist()==['wfo_best','public_zone_wfo','coastal_marine_zone_wfo','offshore_zone_wfo','cwa_synoptic']
    pd.testing.assert_frame_equal(result,normalize_station_metadata(result))
    assert frame.wfo_best.iloc[1]==''


def test_ndbc_alias_requires_same_station_id_suffix_nearby_coordinates_and_unambiguous_wfo():
    frame=pd.DataFrame(dict(station_id=['RIXA2','NDBCRIXA2','OTHER','NDBCOTHER','FAR','NDBCFAR',None],
        wfo_best=['AJK',None,'AFC',None,'AFG',None,None],
        latitude=[58.17706,58.17706,60.,np.nan,60.,65.,np.nan],
        longitude=[-135.05154,-135.05154,-150.,-150.,-150.,-150.,np.nan]))
    result=normalize_station_metadata(frame)
    assert result.wfo_best.iloc[1]=='AJK'
    assert result.wfo_assignment_source.iloc[1]=='coordinate-checked alias:RIXA2'
    assert result.wfo_best.iloc[[3,5,6]].isna().all()
    assert result.station_id.tolist()==frame.station_id.astype('string').tolist()
    conflict=pd.DataFrame(dict(station_id=['BASE','BASE','NDBCBASE'],wfo_best=['AJK','AFC',None],
                              latitude=[60.]*3,longitude=[-150.]*3))
    assert pd.isna(normalize_station_metadata(conflict).wfo_best.iloc[2])


def test_fallback_keeps_metadata_ids_independent_and_missing_stations_are_not_invented():
    frame=pd.DataFrame(dict(station_id=['RIXA2'],wfo_best=['AJK'],latitude=[58.],longitude=[-135.]))
    assert normalize_station_metadata(frame).station_id.tolist()==['RIXA2']


def test_offset_examples_day_rollover_tolerances_and_source_elements():
    nbm=typical_hours('nbm','wind');qmd=typical_hours('nbmqmd','wind');ndfd=typical_hours('ndfd','wind')
    assert nbm==[1,7,13,19] and ndfd==[0,12]
    assert typical_hours('nbm','mint')==qmd
    assert typical_hours('nbm','minrh')==[0,12]
    rows=cycle_matches(ndfd,nbm,-5,0)
    assert all(row['compatible'] for row in rows)
    assert rows[0]['b_hour']==19 and rows[0]['b_day']==-1
    assert rows[1]['b_hour']==7 and rows[1]['b_day']==0
    assert not any(row['compatible'] for row in cycle_matches(ndfd,nbm,-6,0))
    assert all(row['compatible'] for row in cycle_matches(ndfd,nbm,-6,1))
    assert all(row['compatible'] for row in cycle_matches(ndfd,qmd,-6,0))
    assert cycle_matches(ndfd,nbm,0,1)[0]['actual_offset']==1
    assert earlier_offsets(0,nbm)==[-5,-11,-17,-23]
    assert earlier_offsets(0,qmd)==[0,-6,-12,-18]
    assert len([r for r in cycle_matches(nbm,ndfd,-1,0) if r['compatible']])==2
    assert cycle_matches([0],qmd,-72,0)[0]['b_day']==-3


def test_guide_button_updates_controls_without_running_comparison():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(ROOT/'pages/4_Model_Comparison.py'),default_timeout=20).run()
    assert not app.exception
    app.selectbox(key='compare_element').set_value('wind').run()
    app.number_input(key='compare_ref_tolerance').set_value(0.).run()
    assert any('typical run schedules do not align' in warning.value for warning in app.warning)
    assert 'compare_result' not in app.session_state
    button=next(b for b in app.button if b.label=='Use this offset')
    button.click().run()
    assert not app.exception
    assert app.checkbox(key='compare_use_offset').value
    assert app.number_input(key='compare_offset').value==-5
    assert not any('typical run schedules do not align' in warning.value for warning in app.warning)
    assert 'compare_result' not in app.session_state


def test_marine_fallback_station_is_included_in_ajk_map_query(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import data_loader
    frame=pd.DataFrame(dict(station_id=['NDBCRIXA2','OTHER'],wfo_best=[None,'AFC'],
        coastal_marine_zone_wfo=['AJK',None],latitude=[58.,60.],longitude=[-135.,-150.]))
    path=tmp_path/'stations.parquet';frame.to_parquet(path)
    requests=[]
    def fetch(**kwargs):
        requests.append(kwargs['station_list'])
        return pd.DataFrame(),pd.DataFrame(),'Synthetic empty archive'
    monkeypatch.setattr(data_loader,'fetch_data',fetch)
    app=AppTest.from_file(str(ROOT/'pages/1_Map_Explorer.py'),default_timeout=20).run()
    app.secrets.setdefault('local',{})['metadata_path']=str(path)
    app.run()
    app.selectbox(key='map_wfo').set_value('AJK').run()
    next(b for b in app.button if b.label=='Build Station Metric Map').click().run()
    assert not app.exception
    assert requests[-1]==['NDBCRIXA2']
