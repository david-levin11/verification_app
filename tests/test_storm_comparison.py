"""Single-run comparisons share the established target/reference/obs matcher."""
from datetime import date
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from storm_comparison import (compare_storm_runs, storm_comparison_summary,
                              plot_comparison_station, plot_comparison_evolution)
from test_nbm_deterministic import deterministic_frames, archive_fixture
from config import get_percentile_columns
from test_storm_analysis import frames


@pytest.mark.parametrize('element',['wind','maxt','mint','precip6hr','precip24hr'])
@pytest.mark.parametrize('reverse',[False,True])
def test_mixed_models_use_identical_observations_and_point_scores(element,reverse):
    m,o,q=deterministic_frames(element)
    init=pd.Timestamp('2026-06-29')
    m['init_time']=init
    m['forecast_hour']=(m.valid_time-init).dt.total_seconds()/3600
    if 'valid_time' not in o:o['valid_time']=o.window_end
    a,b,ma,mb,pa,pb=(q,m,'nbmqmd','nbm','50',None) if reverse else (m,q,'nbm','nbmqmd',None,'50')
    shared,d=compare_storm_runs(a,b,o,ma,mb,element,init,pa,pb)
    assert len(shared)==4 and d['selected_b_init']==init
    assert shared.a_error.eq(0).all() and shared.b_error.eq(0).all()
    assert shared.absolute_error_difference.eq(0).all()
    summary=storm_comparison_summary(shared,shared.target_time.drop_duplicates().sort_values())
    assert summary.n.tolist()==[2,2]
    figure=plot_comparison_station(shared,'A',ma,mb,element,pa,pb,1)
    assert len(figure.axes[0].patches)==2
    assert len(figure.axes[0].collections[-1].get_offsets())==2
    plt.close(figure)
    figure=plot_comparison_evolution(summary,'A','B','kt');plt.close(figure)


def test_offset_uses_single_run_and_preserves_missing_three_hour_steps():
    init=pd.Timestamp('2026-10-01')
    times=pd.date_range(init+pd.Timedelta(hours=3),periods=4,freq='3h')
    a=pd.DataFrame(dict(station_id='A',valid_time=times,init_time=init,wind_speed_kt=10.))
    b=a.iloc[::2].copy();b.init_time=init-pd.Timedelta(hours=6);b.wind_speed_kt=12.
    other=a.copy();other.init_time=init-pd.Timedelta(hours=5);other.wind_speed_kt=999.
    observations=pd.DataFrame(dict(stid='A',valid_time=times-pd.Timedelta(minutes=7),obs_wind_speed_kts=11.))
    shared,d=compare_storm_runs(a,pd.concat([b,other]),observations,'nbm','hrrr','wind',init,
        offset_hours=-6,reference_tolerance='1h')
    assert len(shared)==2 and d['a_unmatched']==2
    assert shared.b_init_time.eq(init-pd.Timedelta(hours=6)).all()
    assert shared.b_model_value.eq(12).all()
    assert shared.obs_time_offset_minutes.eq(-7).all()
    targets=pd.Series(times)
    summary=storm_comparison_summary(shared,targets)
    assert summary.n.tolist()==[1,0,1,0]
    assert summary.a_mae.isna().tolist()==[False,True,False,True]
    assert storm_comparison_summary(shared,targets,True).n.eq(0).all()
    absent,d=compare_storm_runs(a,b,observations,'nbm','hrrr','wind',init,offset_hours=0)
    assert absent.empty and d['selected_b_init'] is None
    absent,d=compare_storm_runs(a,b.iloc[:0],observations,'nbm','hrrr','wind',init)
    assert absent.empty


def test_precipitation_requires_correct_observation_duration():
    m,o,q=deterministic_frames('precip24hr')
    o['start_time']=o.end_time-pd.Timedelta(hours=6)
    shared,d=compare_storm_runs(m,q,o,'nbm','nbmqmd','precip24hr',m.init_time.iloc[0],None,'50')
    assert shared.empty and d['missing_observations']==4


def test_ndfd_references_long_leads_and_difference_sign():
    from storm_visuals import snapshot_map_data
    from test_storm_analysis import metadata
    m,o,q=deterministic_frames('wind')
    init=pd.Timestamp('2026-06-20')
    for frame in [m,q]:
        frame['init_time']=init
        frame['forecast_hour']=(frame.valid_time-init).dt.total_seconds()/3600
    m=m.drop(columns='init_time')
    m['wind_speed_kt']+=3
    shared,d=compare_storm_runs(m,q,o,'ndfd','nbmqmd','wind',init,None,'50')
    assert len(shared)==4 and shared.a_forecast_hour.gt(168).all()
    assert shared.absolute_error_difference.eq(3).all()  # B closer.
    view=shared.assign(absolute_error_difference=[-2.,3.,-1.,0.])
    _,_,limits=snapshot_map_data(view,metadata(),'absolute_error_difference')
    assert limits==(-3,3)
    # Both deterministic forecasts work without any quantile columns.
    scalar=m.assign(init_time=init)
    paired,_=compare_storm_runs(scalar,scalar,o,'nbm','hrrr','wind',init)
    fig=plot_comparison_station(paired,'A','nbm','hrrr','wind',None,None,25)
    assert not fig.axes[0].patches
    plt.close(fig)


def test_both_probabilistic_and_missing_boxes_do_not_remove_observations():
    _,o,q=deterministic_frames('wind')
    shared,_=compare_storm_runs(q,q,o,'nbmqmd','nbmqmd_exp','wind',q.init_time.iloc[0],'75','50')
    assert len(shared)==4
    figure=plot_comparison_station(shared,'A','nbmqmd','nbmqmd_exp','wind','75','50',25)
    assert len(figure.axes[0].patches)==4
    plt.close(figure)
    shared['a_wind_p10']=999
    figure=plot_comparison_station(shared,'A','nbmqmd','nbmqmd_exp','wind','75','50',25)
    assert len(figure.axes[0].patches)==2
    assert len(figure.axes[0].collections[-1].get_offsets())==2
    plt.close(figure)


@pytest.mark.parametrize('element',['gust','rh'])
def test_gust_and_rh_share_the_same_comparison_path(element):
    a,o=frames(element,True)
    b,_=frames(element,False)
    shared,d=compare_storm_runs(a,b,o,'nbmqmd','hrrr',element,a.init_time.iloc[0],'50')
    assert len(shared)==4 and d['forecast_matches']==4
    fig=plot_comparison_station(shared,'A','nbmqmd','hrrr',element,'50',None,25)
    assert len(fig.axes[0].patches)==2
    if element=='rh':assert fig.axes[0].get_ylim()==(0,100)
    plt.close(fig)


@pytest.mark.parametrize('element',['wind','maxt','precip24hr'])
def test_storm_comparison_page_and_saved_request(tmp_path,monkeypatch,element):
    from streamlit.testing.v1 import AppTest
    import storm_visuals
    _,_,_,metadata=archive_fixture(tmp_path,element)
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kwargs:None)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20).run()
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.text_input(key='storm_Local Archive Root').set_value(str(tmp_path))
    app.text_input(key='storm_metadata').set_value(str(metadata))
    app.selectbox(key='storm_Model').set_value('nbmqmd').run()
    app.selectbox(key='storm_Element').set_value(element).run()
    app.checkbox(key='storm_compare_enabled').set_value(True).run()
    app.selectbox(key='storm_model_b').set_value('nbm').run()
    app.selectbox(key=f'storm_percentile_{element}').set_value('50')
    app.text_input(key='storm_Model Init Time (YYYY-MM-DD HH:MM:SS)').set_value('2026-06-29')
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,6,30))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,7,1))
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error,[x.value for x in app.exception]+[x.value for x in app.error]
    result=app.session_state['storm_result']
    assert len(result['shared'])==4
    assert any(x.label=='Shared matched cases' and x.value=='4' for x in app.metric)
    app.selectbox(key=f'storm_map_display_{element}_True').set_value('Model absolute-error difference').run()
    assert not app.exception
    assert any('Negative values favor A' in x.value for x in app.markdown)
    app.number_input(key='storm_offset_hours').set_value(-6.).run()
    assert app.session_state['storm_result']['context']['offset_hours']==0
    assert any('Controls have changed' in x.value for x in app.info)
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error
    assert app.session_state['storm_result']['shared'].empty
    assert any('No shared verification cases' in x.value for x in app.warning)
