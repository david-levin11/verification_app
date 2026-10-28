"""Archived lead availability, not configured schedules, controls verification."""
from datetime import date
from pathlib import Path
import sys
import pandas as pd
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from config import get_projection_lead_bounds
from data_loader import fetch_data
from comparison_loader import load_comparison_data
from comparison import comparison_cases,lead_group
from storm_analysis import build_storm_cases


INIT=pd.Timestamp('2026-07-01')
HOURS=list(range(0,169,3))


def frame(hours,init=INIT):
    return pd.DataFrame({'station_id':['A']*len(hours),'init_time':init,
        'forecast_hour':hours,'valid_time':[init+pd.Timedelta(hours=h) for h in hours],
        'wind_speed_kt':[float(h) for h in hours]})


def write(root,model,data):
    for month,part in data.groupby(data.valid_time.dt.strftime('%Y_%m') if model=='obs' else data.init_time.dt.strftime('%Y_%m')):
        folder=root/model/'wind';folder.mkdir(parents=True,exist_ok=True)
        part.to_parquet(folder/f'{month}_archive.parquet',index=False)


def archives(root):
    a=frame(HOURS);b=frame(list(range(0,169,6)))
    write(root,'ndfd',a);write(root,'nbm',b)
    obs=pd.DataFrame({'stid':['A']*len(a),'valid_time':a.valid_time-pd.Timedelta(minutes=7),'obs_wind_speed_kts':a.wind_speed_kt})
    write(root,'obs',obs)
    return a,b


@pytest.mark.parametrize('day',range(1,8))
def test_every_three_hour_projection_in_its_day_without_neighbor_boundary(tmp_path,day):
    archives(tmp_path)
    lo,hi=get_projection_lead_bounds(f'Day {day}',f'Day {day}')
    m,o,_=fetch_data('Aggregate Verification','ndfd','obs',date(2026,7,1),date(2026,7,8),['A'],None,None,{},None,
        'wind',tmp_path,'15min',forecast_lead_range=(lo,hi))
    expected=[h for h in HOURS if (h>=lo if lo==0 else h>lo) and h<=hi]
    assert sorted(m.forecast_hour)==expected
    assert lead_group(m.forecast_hour).tolist()==[day]*len(expected)
    assert len(expected)==(9 if day==1 else 8)


def test_all_hours_and_storm_include_every_record_without_static_schedules(tmp_path):
    archives(tmp_path)
    for mode in ['Map Explorer','Aggregate Verification','Storm Specific Zoom']:
        m,o,_=fetch_data(mode,'ndfd','obs',date(2026,7,1),date(2026,7,8),['A'],None,INIT,{},None,'wind',tmp_path,'15min')
        assert sorted(m.forecast_hour)==HOURS
        cases=build_storm_cases(m,o,'ndfd','obs','wind',INIT,tolerance='15min')
        assert len(cases)==57 and cases.obs_value.notna().all()


def test_three_hour_model_matches_only_actual_six_hour_targets_and_retains_day7(tmp_path):
    archives(tmp_path)
    a,b,o,_=load_comparison_data(tmp_path,'ndfd','nbm','obs','wind',date(2026,7,1),date(2026,7,8),['A'])
    c,d=comparison_cases(a,b,o,'ndfd','nbm','wind',lead_max=168,obs_time_tolerance='15min')
    assert len(a)==57 and len(b)==29 and len(c)==29
    assert d['a_unmatched']==28
    assert sorted(c.a_forecast_hour)==list(range(0,169,6))
    assert c.lead_day.value_counts().sort_index().to_dict()=={1:5,2:4,3:4,4:4,5:4,6:4,7:4}
    assert c.a_valid_time.eq(c.b_valid_time).all()
    assert c.a_model_value.eq(c.obs_value).all()
    # Sparse archives are legitimate: no filling/interpolation of missing steps.
    sparse=b[~b.forecast_hour.isin([24,60,168])]
    c,d=comparison_cases(a,sparse,o,'ndfd','nbm','wind',lead_max=168)
    assert len(c)==26 and d['a_unmatched']==31
    assert not c.a_forecast_hour.isin([24,60,168]).any()


def test_reference_offset_changes_b_leads_not_shared_valid_targets(tmp_path):
    a,b=archives(tmp_path)
    # A is 3-hourly from 00Z; the older B run is 6-hourly from previous 18Z.
    b['init_time']-=pd.Timedelta(hours=6)
    b['forecast_hour']+=6
    o=pd.DataFrame({'stid':['A']*len(a),'valid_time':a.valid_time-pd.Timedelta(minutes=7),'obs_wind_speed_kts':a.wind_speed_kt})
    c,_=comparison_cases(a,b,o,'ndfd','nbm','wind',offset_hours=-6,lead_max=168)
    assert len(c)==29 and c.actual_offset_hours.eq(-6).all()
    assert c.b_forecast_hour.eq(c.a_forecast_hour+6).all()
    assert c.a_valid_time.eq(c.b_valid_time).all()


@pytest.mark.parametrize('statistics',[True,False])
def test_all_mode_discovers_long_lead_in_older_initialization_month(tmp_path,statistics):
    # A 240-hour row on June 10 lives in May. A fixed seven-day lookback misses it.
    m=frame([240],pd.Timestamp('2026-05-31'))
    folder=tmp_path/'nbm/wind';folder.mkdir(parents=True)
    m.to_parquet(folder/'2026_05_archive.parquet',index=False,write_statistics=statistics)
    write(tmp_path,'obs',pd.DataFrame({'stid':['A'],'valid_time':m.valid_time,'obs_wind_speed_kts':[240.]}))
    loaded,_,_=fetch_data('Map Explorer','nbm','obs',date(2026,6,10),date(2026,6,10),['A'],None,None,{},None,'wind',tmp_path)
    assert loaded.forecast_hour.tolist()==[240]


def test_continuous_day_bounds_keep_irregular_and_fractional_archived_leads(tmp_path):
    m=frame([23.,24.,24.5,27.,48.,48.5])
    write(tmp_path,'nbm',m)
    write(tmp_path,'obs',pd.DataFrame({'stid':['A']*len(m),'valid_time':m.valid_time,'obs_wind_speed_kts':m.wind_speed_kt}))
    loaded,_,_=fetch_data('Aggregate Verification','nbm','obs',date(2026,7,1),date(2026,7,4),['A'],None,None,{},None,
        'wind',tmp_path,forecast_lead_range=(24,48))
    assert loaded.forecast_hour.tolist()==[24.5,27.,48.]
    np.testing.assert_array_equal(lead_group(pd.Series([0,24,24.5,48,48.5,144,144.5,168])),[1,1,2,2,3,6,7,7])


@pytest.mark.parametrize('page',['map','aggregate'])
def test_page_controls_day7_and_all_use_actual_three_hour_archives(tmp_path,page):
    from streamlit.testing.v1 import AppTest
    from test_storm_analysis import metadata
    a,_=archives(tmp_path);write(tmp_path,'nbm',a)
    path=tmp_path/'metadata.parquet';metadata().iloc[[0]].to_parquet(path,index=False)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20).run()
    app.switch_page('pages/1_Map_Explorer.py' if page=='map' else 'pages/2_Aggregate_Verification.py').run()
    if page=='map':app.text_input(key='map_metadata_path').set_value(str(path)).run()
    else:app.text_input(key='aggregate_station_ids_input').set_value('A')
    app.text_input(key=f'{page}_ui_archive_root').set_value(str(tmp_path))
    app.selectbox(key=f'{page}_ui_model').set_value('nbm').run()
    app.selectbox(key=f'{page}_ui_element').set_value('wind').run()
    app.date_input(key=f'{page}_ui_start_date').set_value(date(2026,7,1))
    app.date_input(key=f'{page}_ui_end_date').set_value(date(2026,7,8))
    app.checkbox(key=f'{page}_ui_use_all_forecast_hours').set_value(False).run()
    app.selectbox(key=f'{page}_ui_forecast_projection_start').set_value('Day 7')
    app.selectbox(key=f'{page}_ui_forecast_projection_end').set_value('Day 7').run()
    button='Build Station Metric Map' if page=='map' else 'Run Aggregate Verification'
    def count():
        assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
        return int(app.session_state['station_metrics'].n.sum()) if page=='map' else app.session_state['aggregate_summary']['n']
    next(b for b in app.button if b.label==button).click().run(timeout=30)
    assert count()==8
    app.checkbox(key=f'{page}_ui_use_all_forecast_hours').set_value(True).run()
    next(b for b in app.button if b.label==button).click().run(timeout=30)
    assert count()==57


def test_comparison_page_defaults_to_day7_and_skips_missing_three_hour_steps(tmp_path):
    from streamlit.testing.v1 import AppTest
    archives(tmp_path)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/pages/4_Model_Comparison.py'),default_timeout=20).run()
    app.text_input(key='compare_archive_root').set_value(str(tmp_path))
    app.text_input(key='compare_stations').set_value('A')
    app.date_input(key='compare_start').set_value(date(2026,7,1))
    app.date_input(key='compare_end').set_value(date(2026,7,8))
    assert app.number_input(key='compare_lead_max').value==168
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
    c=app.session_state['comparison_result']['cases']
    assert len(c)==29 and c.a_forecast_hour.max()==168
    assert sorted(c[c.lead_day.eq(7)].a_forecast_hour)==[150,156,162,168]
