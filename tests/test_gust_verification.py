"""Gust archives may be dedicated or combined with wind, including across months."""
from datetime import date
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt

ROOT = Path(__file__).parents[1]/'web_app'
sys.path.insert(0, str(ROOT))
from archive_files import resolve_archive_paths, gust_observation_coverage
from config import MODELS, get_available_elements, get_forecast_hours, is_probabilistic
from data_loader import fetch_data
from comparison_loader import load_comparison_data
from comparison import comparison_cases, comparison_scores
from pairing import build_verification_pairs
from plots import plot_storm_timeseries


def write(root, model, element, month, frame, legacy=False):
    folder = root/model/element
    folder.mkdir(parents=True, exist_ok=True)
    name = f'{month}_{model}_{element}_archive.parquet' if legacy else f'{month}_archive.parquet'
    path = folder/name
    frame.to_parquet(path, index=False)
    return str(path)


def gusts(times=None, values=None):
    valid = pd.to_datetime(times or ['2026-05-02 00:00','2026-05-02 06:00','2026-05-02 12:00'])
    return pd.DataFrame(dict(station_id=['A']*len(valid), init_time=[pd.Timestamp('2026-05-01')]*len(valid),
        valid_time=valid, forecast_hour=(valid-pd.Timestamp('2026-05-01')).total_seconds()/3600,
        wind_speed_kt=[2.]*len(valid), wind_gust_kt=values if values is not None else [0.,40.,50.]))


def fixture(root):
    frame = gusts()
    write(root,'nbm','wind','2026_05',frame)
    write(root,'hrrr','wind','2026_05',frame)
    write(root,'urma','wind','2026_05',frame.assign(init_time=frame.valid_time, forecast_hour=0))
    write(root,'ndfd','gust','2026_05',frame.drop(columns=['init_time','wind_speed_kt']),legacy=True)
    qmd = frame[['station_id','init_time','valid_time','forecast_hour']].copy()
    for pct in [5,10,25,50,75,90,95]: qmd[f'gust_p{pct}'] = [0.,40.,50.]
    write(root,'nbmqmd','gust','2026_05',qmd)
    obs = pd.DataFrame(dict(stid=['A']*3, valid_time=frame.valid_time-pd.Timedelta(minutes=7),
        obs_wind_speed_kts=[2.,2.,2.], obs_wind_gust_kts=[0.,45.,np.nan], obs_wind_dir_deg=[0.,10.,20.]))
    write(root,'obs','wind','2026_05',obs)
    meta = root/'stations.parquet'
    pd.DataFrame(dict(station_id=['A'],latitude=[58.3],longitude=[-134.5])).to_parquet(meta,index=False)
    return frame, obs, meta


def test_gust_capabilities_use_wind_hours_for_combined_models():
    for model in MODELS:
        assert 'gust' in get_available_elements(model)
        assert get_forecast_hours(model,'gust','All')
    for model in ['nbm','nbm_exp','hrrr','urma']:
        assert not is_probabilistic(model,'gust')
        assert get_forecast_hours(model,'gust','All') == get_forecast_hours(model,'wind','All')
    assert is_probabilistic('nbmqmd','gust')


def test_per_month_precedence_schema_validation_and_no_double_count(tmp_path):
    a=write(tmp_path,'hrrr','wind','2026_05',gusts())
    write(tmp_path,'hrrr','wind','2026_06',gusts(values=[99.,99.,99.]))
    b=write(tmp_path,'hrrr','gust','2026_06',gusts(),legacy=True)
    # An incorrectly named wind-only file cannot supply gusts.
    write(tmp_path,'hrrr','gust','2026_05',gusts().drop(columns='wind_gust_kt'))
    files, missing, warnings = resolve_archive_paths(tmp_path,'hrrr','gust','2026-05-01','2026-06-30')
    assert files == [a,b] and not missing
    assert any('no gust value columns' in m for m in warnings)
    assert any('1 monthly' in m for m in warnings)
    # All-null values in a valid dedicated archive stay missing, rather than
    # silently being filled from another archive.
    c=write(tmp_path,'hrrr','gust','2026_05',gusts(values=[np.nan]*3))
    files,_,_=resolve_archive_paths(tmp_path,'hrrr','gust','2026-05-01','2026-05-31')
    assert files == [c]
    files,missing,_=resolve_archive_paths(tmp_path,'ndfd','gust','2026-05-01','2026-05-31')
    assert not files and len(missing)==1


@pytest.mark.parametrize('model', ['nbm','hrrr','ndfd','nbmqmd','urma'])
def test_both_loaders_use_gust_values_and_keep_zero_not_missing(tmp_path, model):
    fixture(tmp_path)
    m,o,message=fetch_data('Aggregate Verification',model,'obs',date(2026,5,2),date(2026,5,2),
        ['A'],None,None,{},'50' if model=='nbmqmd' else None,element='gust',archive_root=tmp_path,obs_time_tolerance='15min')
    assert len(m)==3 and len(o)==3
    assert '1 of 3' in message and '1 recorded zeros' in message
    paired=build_verification_pairs(m,o,model,'obs','gust','50' if model=='nbmqmd' else None,'15min')
    assert paired.model_value.tolist() == [0,40]
    assert paired.obs_value.tolist() == [0,45]
    assert paired.obs_time_offset_minutes.eq(-7).all()
    a,b,o,warnings=load_comparison_data(tmp_path,'ndfd',model,'obs','gust',date(2026,5,2),date(2026,5,2),['A'],obs_time_tolerance='15min')
    cases,_=comparison_cases(a,b,o,'ndfd',model,'gust',None,'50' if model=='nbmqmd' else None,obs_time_tolerance='15min',reference_tolerance='48h' if model=='urma' else '0h')
    # URMA is an analysis at target time, so a wider reference tolerance is intentional here.
    assert len(cases)==2 and cases.obs_value.tolist()==[0,45]
    scores,sa,sb=comparison_scores(cases,'gust',34,probability_b=model=='nbmqmd')
    assert sa['n']==sb['n']==2
    if model=='nbmqmd': assert sb['n_prob']==2
    assert any('loaded reports' in w for w in warnings)


def test_only_gust_columns_can_be_used_and_nonfinite_gusts_are_excluded(tmp_path):
    write(tmp_path,'nbm','wind','2026_05',gusts().drop(columns='wind_gust_kt'))
    m,o,message=fetch_data('Aggregate Verification','nbm','obs',date(2026,5,2),date(2026,5,2),['A'],None,None,{},None,
        element='gust',archive_root=tmp_path)
    assert m.empty and 'no gust value columns' in message
    m=gusts(values=[0.,np.inf,30.])
    o=pd.DataFrame(dict(stid=['A']*3,valid_time=m.valid_time,obs_wind_gust_kts=[0.,np.inf,np.nan]))
    paired=build_verification_pairs(m,o,'nbm','obs','gust',obs_time_tolerance='0min')
    assert len(paired)==1 and paired.obs_value.iloc[0]==0
    assert '2 of 3' in gust_observation_coverage(o)


def test_loader_union_handles_monthly_schema_changes_and_storm_init_month(tmp_path):
    start=gusts(['2026-05-31 18:00'],[40.])
    finish=gusts(['2026-06-01 06:00'],[50.])
    start['init_time']=finish['init_time']=pd.Timestamp('2026-05-31')
    start['forecast_hour']=18;finish['forecast_hour']=30
    # Both valid times belong to the run's May archive.
    write(tmp_path,'hrrr','wind','2026_05',pd.concat([start,finish],ignore_index=True))
    june=finish.drop(columns='wind_speed_kt').assign(init_time=pd.Timestamp('2026-06-01'),forecast_hour=6,wind_gust_kt=60.)
    write(tmp_path,'hrrr','gust','2026_06',june)
    for month,time in [('05','2026-05-31 17:53'),('06','2026-06-01 05:53')]:
        write(tmp_path,'obs','wind',f'2026_{month}',pd.DataFrame(dict(stid=['A'],valid_time=pd.to_datetime([time]),obs_wind_gust_kts=[45.])))
    m,o,_=fetch_data('Aggregate Verification','hrrr','obs',date(2026,5,31),date(2026,6,1),['A'],None,None,{},None,
        element='gust',archive_root=tmp_path)
    assert sorted(m.wind_gust_kt)==[40,50,60]
    m,o,_=fetch_data('Storm Specific Zoom','hrrr','obs',date(2026,6,1),date(2026,6,1),['A'],[],
        '2026-05-31 00:00',{},None,element='gust',archive_root=tmp_path)
    assert m.wind_gust_kt.tolist()==[50]


def test_urma_gust_verification_uses_exact_analysis_times(tmp_path):
    frame,_,_=fixture(tmp_path)
    m,o,_=fetch_data('Aggregate Verification','hrrr','urma',date(2026,5,2),date(2026,5,2),['A'],None,None,{},None,
        element='gust',archive_root=tmp_path)
    paired=build_verification_pairs(m,o,'hrrr','urma','gust')
    assert len(paired)==3 and paired.model_value.tolist()==[0,40,50]
    assert paired.obs_value.tolist()==[0,40,50]


def test_storm_plot_selects_gust_percentile_units_and_full_end_day(tmp_path):
    frame,obs,_=fixture(tmp_path)
    fig=plot_storm_timeseries(frame,obs,'A','2026-05-01',date(2026,5,2),date(2026,5,2),'hrrr',element='gust')
    assert fig.axes[0].lines[0].get_ydata().tolist()==[0,40,50]
    assert 'Wind Gust (kt)'==fig.axes[0].get_ylabel()
    assert np.isnan(fig.axes[0].lines[1].get_ydata()[-1])
    plt.close(fig)
    qmd=frame.drop(columns=['wind_gust_kt','wind_speed_kt'])
    for pct in [5,10,25,50,75,90,95]:qmd[f'gust_p{pct}']=[pct,pct,pct]
    fig=plot_storm_timeseries(qmd,obs,'A','2026-05-01',date(2026,5,2),date(2026,5,2),'nbmqmd',element='gust',percentile='75')
    assert fig.axes[0].lines[0].get_ydata().tolist()==[75,75,75]
    assert len(fig.axes[0].collections)==2
    plt.close(fig)
    with pytest.raises(ValueError):
        plot_storm_timeseries(frame.drop(columns='wind_gust_kt'),obs,'A','2026-05-01',date(2026,5,2),date(2026,5,2),'hrrr',element='gust')


def test_gust_page_flows_and_minimum_filters(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    _,_,metadata=fixture(tmp_path)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=15).run()
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.text_input(key='map_metadata_path').set_value(str(metadata)).run()
    app.text_input(key='map_ui_archive_root').set_value(str(tmp_path))
    app.selectbox(key='map_ui_model').set_value('hrrr').run()
    app.selectbox(key='map_ui_element').set_value('gust').run()
    app.date_input(key='map_ui_start_date').set_value(date(2026,5,2))
    app.date_input(key='map_ui_end_date').set_value(date(2026,5,2))
    app.checkbox(key='map_ui_use_all_forecast_hours').set_value(True).run()
    next(b for b in app.button if b.label=='Build Station Metric Map').click().run(timeout=30)
    assert not app.exception and not app.error, [e.value for e in app.error]
    assert app.session_state['station_metrics'].n.iloc[0]==2
    assert any('missing/nonfinite gusts' in w.value for w in app.warning)
    app.checkbox(key='map_ui_filter_gust').set_value(True).run()
    next(b for b in app.button if b.label=='Build Station Metric Map').click().run(timeout=30)
    assert not app.exception and app.session_state['station_metrics'].n.iloc[0]==1
    app.switch_page('pages/2_Aggregate_Verification.py').run()
    app.text_input(key='aggregate_ui_archive_root').set_value(str(tmp_path))
    app.text_input(key='aggregate_station_ids_input').set_value('A')
    app.selectbox(key='aggregate_ui_model').set_value('hrrr').run()
    app.selectbox(key='aggregate_ui_element').set_value('gust').run()
    app.date_input(key='aggregate_ui_start_date').set_value(date(2026,5,2))
    app.date_input(key='aggregate_ui_end_date').set_value(date(2026,5,2))
    app.checkbox(key='aggregate_ui_use_all_forecast_hours').set_value(True)
    app.checkbox(key='aggregate_ui_filter_gust').set_value(True).run()
    next(b for b in app.button if b.label=='Run Aggregate Verification').click().run(timeout=30)
    assert not app.exception and app.session_state['aggregate_summary']['n']==1
    app.switch_page('pages/4_Model_Comparison.py').run()
    app.text_input(key='compare_archive_root').set_value(str(tmp_path))
    app.text_input(key='compare_stations').set_value('A')
    app.selectbox(key='compare_element').set_value('gust').run()
    app.date_input(key='compare_start').set_value(date(2026,5,2))
    app.date_input(key='compare_end').set_value(date(2026,5,2))
    app.checkbox(key='compare_filter_gust').set_value(True).run()
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error
    assert len(app.session_state['comparison_result']['cases'])==1
    assert app.session_state['comparison_result']['direction_result'] is None
    app.selectbox(key='compare_model_b').set_value('nbmqmd').run()
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and app.session_state['comparison_result']['summary_b']['n_prob']==1
    import plots
    calls=[]
    original=plots.plot_storm_timeseries
    def capture(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)
    monkeypatch.setattr(plots, 'plot_storm_timeseries', capture)
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.text_input(key='storm_Local Archive Root').set_value(str(tmp_path))
    app.selectbox(key='storm_Element').set_value('gust').run()
    app.text_input(key='storm_Target Station').set_value('A')
    app.text_input(key='storm_Model Init Time (YYYY-MM-DD HH:MM:SS)').set_value('2026-05-01 00:00:00')
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,5,2))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,5,2))
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error
    assert not any('Could not generate' in w.value for w in app.warning)
    assert calls and calls[-1]['element']=='gust'
    assert app.warning  # archive/coverage warnings must not suppress the chart


def test_loader_handles_archive_paths_with_quotes(tmp_path):
    root=tmp_path/"David's archives"
    fixture(root)
    model,observations,message=fetch_data('Aggregate Verification','hrrr','obs',
        date(2026,5,2),date(2026,5,2),['A'],None,None,{},None,element='gust',archive_root=root)
    assert len(model)==3 and len(observations)==3
    assert 'Database error' not in (message or '')
