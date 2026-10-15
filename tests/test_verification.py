import sys
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / 'web_app'))
from probability import quantile_probability, probability_cases, probability_scores, reliability_table
from metrics import compute_summary_metrics, compute_station_metrics
from pairing import build_verification_pairs
LEVELS = [.05,.10,.25,.50,.75,.90,.95]

@pytest.mark.parametrize('operator,expected',[('>=',1),('>',0),('<=',1),('<',0)])
def test_equal_quantiles(operator,expected):
    assert quantile_probability([0]*7,LEVELS,0,operator)==expected

@pytest.mark.parametrize('operator,expected',[('>=',.95),('>',.5),('<=',.5),('<',.05)])
def test_ties(operator,expected):
    assert quantile_probability([0,0,0,0,1,2,3],LEVELS,0,operator)==pytest.approx(expected)

@pytest.mark.parametrize('threshold,expected',[(-1,.95),(10,.05),(2.5,.625)])
def test_tails_and_interpolation(threshold,expected):
    assert quantile_probability([0,1,2,3,4,5,6],LEVELS,threshold)==pytest.approx(expected)

def test_invalid_and_missing_quantiles():
    assert np.isnan(quantile_probability([0,2,1],[.1,.5,.9],1))
    assert np.isnan(quantile_probability([np.nan,1],[.1,.9],1))
    assert quantile_probability([0,np.nan,2],[.1,.5,.9],1)==.5
    with pytest.raises(ValueError): quantile_probability([0,1],[.1,.9],0,'=')

def prob_frame():
    d=pd.DataFrame({'station_id':['A','A','B'],'model_value':[0,1,2],'obs_value':[0,2,1]})
    for level in [5,10,25,50,75,90,95]: d[f'qpf_p{level}']=[0,1,2]
    return d

def test_scores_station_aggregate_agree():
    d=prob_frame()
    summary=compute_summary_metrics(d,1,element='precip6hr',probabilistic=True)
    stations=compute_station_metrics(d,pd.DataFrame(),1,element='precip6hr',probabilistic=True)
    assert summary['n_prob']==3 and summary['brier_score']==0 and summary['reliability_error']==0
    assert np.average(stations.brier_score,weights=stations.n_prob)==summary['brier_score']
    d.loc[1,'obs_value']=0
    assert probability_scores(d,'precip6hr',1)['brier_score']==pytest.approx(1/3)

@pytest.mark.parametrize('operator,hits',[('>=',1),('>',0),('<=',2),('<',1)])
def test_threshold_direction(operator,hits):
    d=pd.DataFrame({'station_id':['A']*3,'model_value':[10,30,50],'obs_value':[10,30,20]})
    assert compute_summary_metrics(d,30,threshold_operator=operator)['hits']==hits

def forecasts(element,time='2026-06-01 06:00'):
    value={'wind':'wind_speed_kt','precip6hr':'precip_accum_6hr','maxt':'max_temp'}[element]
    return pd.DataFrame({'station_id':['A'],'init_time':[pd.Timestamp('2026-06-01')],
        'valid_time':[pd.Timestamp(time)],'forecast_hour':[6],value:[1.]})

def test_wind_53_and_tolerance():
    model=forecasts('wind')
    obs=pd.DataFrame({'stid':['A'],'valid_time':[pd.Timestamp('2026-06-01 05:53')],'obs_wind_speed_kts':[2.]})
    pairs=build_verification_pairs(model,obs,'ndfd','obs','wind',obs_time_tolerance='7min')
    assert pairs.obs_time_offset_minutes.iloc[0]==-7
    for tolerance in ['6min','0min']:
        assert build_verification_pairs(model,obs,'ndfd','obs','wind',obs_time_tolerance=tolerance).empty

def test_accumulation_duration_before_nearest_match():
    model=forecasts('precip6hr'); end=pd.to_datetime(['2026-06-01 05:53','2026-06-01 06:00'])
    obs=pd.DataFrame({'stid':['A','A'],'valid_time':end,'end_time':end,
        'start_time':[end[0]-pd.Timedelta(hours=6),end[1]-pd.Timedelta(hours=24)],'precip_total':[.2,9.]})
    pair=build_verification_pairs(model,obs,'ndfd','obs','precip6hr',obs_time_tolerance='15min')
    assert pair.obs_value.iloc[0]==.2 and pair.obs_time_offset_minutes.iloc[0]==-7
    assert pair.obs_window_end.iloc[0]-pair.obs_window_start.iloc[0]==pd.Timedelta(hours=6)
    assert build_verification_pairs(model,obs,'ndfd','obs','precip6hr',obs_time_tolerance='0min').empty

def test_daily_pairing_keeps_latest():
    obs=pd.DataFrame({'stid':['A','A'],'date':pd.to_datetime(['2026-06-01']*2),
       'valid_time':pd.to_datetime(['2026-06-02 06:00']*2),'tmax':[50.,60.]})
    pair=build_verification_pairs(forecasts('maxt','2026-06-01 18:00'),obs,'ndfd','obs','maxt')
    assert len(pair)==1 and pair.obs_value.iloc[0]==60.

def test_plot_uses_shared_cases():
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from plots import plot_threshold_reliability
    d=prob_frame(); expected=reliability_table(probability_cases(d,'precip6hr',1,'<'))
    fig=plot_threshold_reliability(d,1,'nbmqmd','obs','A','start','end','precip6hr',threshold_operator='<')
    np.testing.assert_allclose(fig.axes[0].lines[0].get_xdata(),expected.mean_forecast)
    np.testing.assert_allclose(fig.axes[0].lines[0].get_ydata(),expected.observed_freq)
    assert 'precip6hr < 1' in fig.axes[0].get_title()
    plt.close(fig)

def test_loader_month_boundary_and_end_day(tmp_path):
    from data_loader import fetch_data
    model=forecasts('wind','2026-06-01 00:00');extra=model.copy();extra.valid_time=pd.Timestamp('2026-06-01 23:00')
    directory=tmp_path/'ndfd'/'wind';directory.mkdir(parents=True)
    pd.concat([model,extra]).to_parquet(directory/'2026_06_archive.parquet',index=False)
    obsdir=tmp_path/'obs'/'wind';obsdir.mkdir(parents=True)
    for month,time in [('05','2026-05-31 23:53'),('06','2026-06-01 22:53')]:
        pd.DataFrame({'stid':['A'],'valid_time':[pd.Timestamp(time)],'obs_wind_speed_kts':[2.]}).to_parquet(obsdir/f'2026_{month}_archive.parquet',index=False)
    m,o,msg=fetch_data('Aggregate Verification','ndfd','obs',date(2026,6,1),date(2026,6,1),
        ['A'],None,None,{},None,archive_root=tmp_path,obs_time_tolerance='15min')
    assert len(m)==2 and len(o)==2
    assert len(build_verification_pairs(m,o,'ndfd','obs','wind',obs_time_tolerance='15min'))==2

def test_streamlit_aggregate_probability_controls(tmp_path):
    from streamlit.testing.v1 import AppTest
    model=prob_frame().iloc[[0]].copy()
    model['station_id']='A';model['init_time']=pd.Timestamp('2025-10-01')
    model['valid_time']=pd.Timestamp('2025-10-01 12:00');model['forecast_hour']=12
    for level in [5,10,25,50,75,90,95]: model[f'wind_p{level}']=0.
    folder=tmp_path/'nbmqmd'/'wind';folder.mkdir(parents=True)
    model.to_parquet(folder/'2025_10_archive.parquet',index=False)
    folder=tmp_path/'obs'/'wind';folder.mkdir(parents=True)
    pd.DataFrame({'stid':['A'],'valid_time':[pd.Timestamp('2025-10-01 11:53')],
                  'obs_wind_speed_kts':[0.]}).to_parquet(folder/'2025_10_archive.parquet',index=False)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/pages/2_Aggregate_Verification.py')).run()
    assert not app.exception
    app.selectbox(key='aggregate_ui_model').set_value('nbmqmd').run()
    app.text_input(key='aggregate_ui_archive_root').set_value(str(tmp_path))
    app.text_input(key='aggregate_station_ids_input').set_value('A')
    app.date_input(key='aggregate_ui_end_date').set_value(date(2025,10,1))
    app.number_input(key='aggregate_ui_obs_tolerance_minutes').set_value(15)
    app.selectbox(key='aggregate_ui_threshold_operator_wind').set_value('<')
    app.run()
    next(b for b in app.button if b.label == "Run Aggregate Verification").click().run(timeout=20)
    assert not app.exception
    assert app.session_state['aggregate_summary']['n_prob']==1
    assert app.session_state['aggregate_summary']['brier_score']==0
    assert app.session_state['aggregate_merged'].obs_time_offset_minutes.iloc[0]==-7
    assert not any('Could not create reliability' in w.value for w in app.warning)
    # Changing model/element directly on this page keeps prior results readable.
    app.selectbox(key='aggregate_ui_element').set_value('rh').run()
    assert not app.exception
    app.selectbox(key='aggregate_ui_model').set_value('ndfd').run()
    assert not app.exception
    assert app.session_state['aggregate_summary']['n_prob'] == 1
    # Station map uses the same probability calculation and tolerance controls.
    metadata=tmp_path/'stations.parquet'
    pd.DataFrame({'station_id':['A'],'latitude':[58.3],'longitude':[-134.5],
                  'name':['Test station']}).to_parquet(metadata,index=False)
    map_app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/pages/1_Map_Explorer.py')).run()
    map_app.text_input(key='map_metadata_path').set_value(str(metadata)).run()
    map_app.selectbox(key='map_ui_model').set_value('nbmqmd').run()
    map_app.text_input(key='map_ui_archive_root').set_value(str(tmp_path))
    map_app.date_input(key='map_ui_end_date').set_value(date(2025,10,1))
    map_app.number_input(key='map_ui_obs_tolerance_minutes').set_value(15)
    map_app.selectbox(key='map_ui_threshold_operator_wind').set_value('<')
    map_app.run()
    map_app.selectbox(key='map_selected_metric').set_value('brier_score').run()
    map_app.session_state['selected_station_list'] = ['HIDDEN']
    next(b for b in map_app.button if b.label == "Build Station Metric Map").click().run(timeout=20)
    assert not map_app.exception
    assert map_app.session_state['station_metrics'].brier_score.iloc[0]==0
    assert map_app.session_state['selected_station_list'] == ['HIDDEN']

def test_configured_categories_and_lower_event_defaults():
    from config import CATEGORY_CONFIG, get_element_config
    for category in CATEGORY_CONFIG.values():
        assert len(category['bins'])-1 == len(category['labels'])
    assert get_element_config('rh')['threshold_operator']=='<='
    assert get_element_config('mint')['threshold_operator']=='<='
