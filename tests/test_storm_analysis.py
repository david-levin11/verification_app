"""Single-run matching, archived percentile ranks, maps, and storm page flows."""
from datetime import date
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).parents[1]/'web_app'
sys.path.insert(0,str(ROOT))
from config import get_percentile_columns
from storm_analysis import (observed_percentile,build_storm_cases,interval_summary,
                            evolution_summary,available_intervals)
from storm_visuals import snapshot_map_data,plot_evolution


def frames(element='wind', probabilistic=True):
    rows=[];observations=[]
    for station,adjust in [('A',0),('B',10)]:
        for lead in [12,24]:
            valid=pd.Timestamp('2026-05-01')+pd.Timedelta(hours=lead)
            row=dict(station_id=station,init_time=pd.Timestamp('2026-05-01'),
                     valid_time=valid,forecast_hour=lead)
            values=dict(zip(['5','10','25','50','75','90','95'],[0,5,10,20,30,40,50]))
            if probabilistic:
                for p,col in get_percentile_columns(element).items():row[col]=values[p]+adjust
            else:
                row[{'wind':'wind_speed_kt','gust':'wind_gust_kt','rh':'rh'}[element]]=20+adjust
                if element=='wind':row['wind_dir_deg']=359.
            rows.append(row)
            observation=dict(stid=station,valid_time=valid-pd.Timedelta(minutes=7))
            observation[{'wind':'obs_wind_speed_kts','gust':'obs_wind_gust_kts','rh':'rh'}[element]]=20+adjust
            if element=='wind':observation['obs_wind_dir_deg']=1.
            observations.append(observation)
    return pd.DataFrame(rows),pd.DataFrame(observations)


def metadata():
    return pd.DataFrame(dict(station_id=['A','B'],latitude=[58.3,58.4],longitude=[-134.5,-134.6],
                             mnet_id=['332','96'],elevation_ft=[20.,100.]))


@pytest.mark.parametrize('element',['wind','gust','rh'])
def test_tolerant_matching_and_interval_coverage_share_stations(element):
    m,o=frames(element)
    c=build_storm_cases(m,o,'nbmqmd','obs',element,'2026-05-01','50',tolerance='15min',threshold=25)
    assert len(c)==4 and c.obs_value.notna().all()
    assert c.obs_time_offset_minutes.eq(-7).all()
    assert c.observed_percentile.eq(50).all()
    snapshot=c[c.forecast_hour.eq(12)]
    summary=interval_summary(snapshot)
    assert summary.stations.eq(2).all() and summary.coverage_percent.eq(100).all()
    assert summary.mean_width.tolist()==[20.,35.,50.]
    # One missing bound removes that station from ALL interval summaries.
    c.loc[c.station_id.eq('A'),'width_5_95']=np.nan
    summary=interval_summary(c[c.forecast_hour.eq(12)])
    assert summary.stations.eq(1).all()
    narrow=build_storm_cases(m,o,'nbmqmd','obs',element,'2026-05-01','50',tolerance='6min')
    assert narrow.obs_value.isna().all()
    assert narrow.width_25_75.notna().all()
    assert interval_summary(narrow).stations.eq(0).all()


def test_rank_ties_tails_and_invalid_distributions():
    levels=[5,10,25,50,75,90,95]
    zero=observed_percentile([0]*7,levels,0)
    assert zero[:3]==(50.,5.,95.) and 'tied' in zero[3]
    assert observed_percentile([0,0,0,10,20,30,40],levels,0)[1:3]==(5.,25.)
    below=observed_percentile([0,5,10,20,30,40,50],levels,-1)
    assert below[0]==5 and np.isnan(below[1]) and below[3]=='Below p5'
    above=observed_percentile([0,5,10,20,30,40,50],levels,60)
    assert above[0]==95 and np.isnan(above[2]) and above[3]=='Above p95'
    assert observed_percentile([0,10,5],[5,50,95],8)[3]=='Invalid/insufficient quantiles'
    assert observed_percentile([10],[50],8)[3]=='Invalid/insufficient quantiles'
    assert observed_percentile([0,10],[5,95],5)[0]==50
    assert observed_percentile([0,10],[5,95],np.nan)[3]=='No matched observation'


@pytest.mark.parametrize('element',['wind','gust','rh'])
def test_nonfinite_nearest_report_does_not_hide_a_valid_report(element):
    m,o=frames(element)
    invalid=o.iloc[[0]].copy()
    invalid['valid_time']=m.valid_time.iloc[0]
    invalid[{'wind':'obs_wind_speed_kts','gust':'obs_wind_gust_kts','rh':'rh'}[element]]=np.inf
    o=pd.concat([o,invalid],ignore_index=True)
    c=build_storm_cases(m,o,'nbmqmd','obs',element,'2026-05-01','50')
    first=c[c.station_id.eq('A') & c.forecast_hour.eq(12)].iloc[0]
    assert first.obs_value==20 and first.obs_time_offset_minutes==-7


def test_zero_missing_crossing_and_lower_tail_rh_probability():
    m,o=frames('rh')
    columns=list(get_percentile_columns('rh').values())
    m.loc[0,columns]=0
    o.loc[0,'rh']=0
    m.loc[1,columns[2]]=100  # crossing p25 with higher percentiles
    o.loc[2,'rh']=np.nan
    c=build_storm_cases(m,o,'nbmqmd','obs','rh','2026-05-01','50',threshold=20,operator='<=')
    zero=c[c.station_id.eq('A') & c.forecast_hour.eq(12)].iloc[0]
    assert zero.obs_value==0 and zero.width_25_75==0 and 'tied' in zero.rank_label
    assert zero.forecast_probability==1
    bad=c[c.station_id.eq('A') & c.forecast_hour.eq(24)].iloc[0]
    assert not bad.distribution_valid and np.isnan(bad.forecast_probability) and np.isnan(bad.width_25_75)
    assert c.obs_value.isna().sum()==1


def test_missing_median_is_not_substituted_with_selected_percentile():
    m,o=frames()
    m=m.drop(columns='wind_p50')
    c=build_storm_cases(m,o,'nbmqmd','obs','wind','2026-05-01','75')
    assert c.model_value.iloc[0]==30 and c.error.iloc[0]==10
    assert c.median_value.isna().all() and c.median_error.isna().all()
    assert c.observed_percentile.eq(50).all()  # interpolation remains possible
    assert snapshot_map_data(c[c.forecast_hour.eq(12)],metadata(),'median_error')[0].empty


def test_single_initialization_duplicates_ndfd_and_direction_wrap():
    m,o=frames('wind',False)
    other=m.copy();other['init_time']=pd.Timestamp('2026-04-30')
    m=pd.concat([m,m.iloc[[0]].assign(wind_speed_kt=21),other],ignore_index=True)
    c=build_storm_cases(m,o,'hrrr','obs','wind','2026-05-01',tolerance='15min')
    assert len(c)==4 and c.angular_error.eq(2).all()
    assert c.loc[c.station_id.eq('A') & c.forecast_hour.eq(12),'model_value'].iloc[0]==21
    assert available_intervals(c)==[]
    n=build_storm_cases(m.iloc[:4].drop(columns='init_time'),o,'ndfd','obs','wind','2026-05-01')
    assert len(n)==4
    assert build_storm_cases(m,o,'hrrr','obs','wind','2026-05-03').empty


def test_balanced_evolution_uses_intersection_and_counts_missing_reports():
    m,o=frames()
    o=o.drop(index=1)
    c=build_storm_cases(m,o,'nbmqmd','obs','wind','2026-05-01','50')
    varying=evolution_summary(c)
    fixed=evolution_summary(c,True)
    assert varying.matched_stations.tolist()==[2,1]
    assert fixed.matched_stations.tolist()==[1,1]
    assert fixed.interval_stations.tolist()==[1,1]
    absent=build_storm_cases(m,pd.DataFrame(),'nbmqmd','obs','wind','2026-05-01','50')
    assert len(absent)==4 and absent.obs_value.isna().all()
    assert evolution_summary(absent,True).empty


def test_snapshot_map_censored_ranks_missing_coordinates_and_no_global_selection():
    m,o=frames();o.loc[0,'obs_wind_speed_kts']=100
    c=build_storm_cases(m,o,'nbmqmd','obs','wind','2026-05-01','50')
    snap=c[c.forecast_hour.eq(12)]
    data,view,limits=snapshot_map_data(snap,metadata(),'observed_percentile')
    assert len(data)==2 and limits==(0,100) and view['zoom']>6
    assert data.loc[data.station_id.eq('A'),'metric_value_text'].iloc[0]=='Above p95'
    data,_,_=snapshot_map_data(snap,metadata().iloc[:1],'error')
    assert len(data)==1
    assert snapshot_map_data(snap,pd.DataFrame(),'error')[0].empty
    data,_,limits=snapshot_map_data(snap,metadata(),'forecast_probability')
    assert limits==(0,1) and data.event_outline_color.notna().all()


@pytest.mark.parametrize('element,model,probabilistic',[('wind','nbmqmd',True),('gust','nbmqmd',True),
                                                     ('rh','nbm',True),('rh','hrrr',False)])
def test_storm_page_load_snapshots_evolution_and_station_detail(tmp_path,monkeypatch,element,model,probabilistic):
    from streamlit.testing.v1 import AppTest
    import storm_visuals
    m,o=frames(element,probabilistic)
    for name,frame in [(model,m),('obs',o)]:
        folder=tmp_path/name/element;folder.mkdir(parents=True,exist_ok=True)
        frame.to_parquet(folder/'2026_05_archive.parquet',index=False)
    meta=tmp_path/'metadata.parquet';metadata().to_parquet(meta)
    events={'event':None};renders=[]
    def fake_map(**kwargs):
        renders.append(kwargs)
        return events['event']
    monkeypatch.setattr(storm_visuals,'_station_map',fake_map)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=15).run()
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.text_input(key='storm_Local Archive Root').set_value(str(tmp_path))
    app.text_input(key='storm_metadata').set_value(str(meta))
    app.selectbox(key='storm_Model').set_value(model).run()
    app.selectbox(key='storm_Element').set_value(element).run()
    app.text_input(key='storm_Model Init Time (YYYY-MM-DD HH:MM:SS)').set_value('2026-05-01 00:00:00')
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,5,1))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,5,2))
    app.session_state['selected_station_list']=['A','B']
    app.radio(key='storm_station_scope').set_value('Map Explorer selections').run()
    assert list(app.radio(key='storm_station_scope').options)==['Filtered metadata stations','Map Explorer selections']
    assert not any(x.label in ['Target Station','Station IDs (comma-separated)'] for x in app.text_input)
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error, [x.value for x in app.exception]+[x.value for x in app.error]
    assert len(app.session_state['storm_result']['cases'])==4
    assert renders and renders[-1]['records'][0]['obs_time_offset_minutes']==-7
    assert app.selectbox(key='storm_detail_station').value=='A'
    events['event']=dict(event_id='click-B',clicked_station_id='B',station_ids=['A','B'])
    app.run()
    assert not app.exception
    assert app.selectbox(key='storm_detail_station').value=='B'
    assert app.session_state['selected_station_list']==['A','B']
    app.checkbox(key='storm_balanced').set_value(True).run()
    assert not app.exception
    # Input edits must not silently relabel saved results.
    app.sidebar.number_input(key=f'storm_threshold_{element}').set_value(99.).run()
    assert app.session_state['storm_result']['context']['threshold']!=99
    assert any('Controls have changed' in x.value for x in app.info)
