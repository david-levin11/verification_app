import sys
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from comparison import (comparison_cases,match_forecasts,comparison_scores,prepare_forecasts,
                        grouped_scores,paired_mae_interval)
from comparison_loader import load_comparison_data


def wind(init, valid, value, station='A', ndfd=False):
    init,valid=pd.Timestamp(init),pd.Timestamp(valid)
    row=dict(station_id=station,valid_time=valid,forecast_hour=(valid-init).total_seconds()/3600,
             wind_speed_kt=value)
    if not ndfd:row['init_time']=init
    return row


def observations(times,values,stations=None):
    return pd.DataFrame({'stid':stations or ['A']*len(times),
        'valid_time':pd.to_datetime(times),'obs_wind_speed_kts':values})


def test_ndfd_reference_uses_valid_minus_step():
    f=pd.DataFrame([wind('2026-06-01','2026-06-02',10,ndfd=True)])
    assert prepare_forecasts(f,'ndfd','wind').init_time.iloc[0]==pd.Timestamp('2026-06-01')


def test_offset_same_valid_and_shared_53_observation():
    a=pd.DataFrame([wind('2026-06-01','2026-06-02',20,ndfd=True)])
    b=pd.DataFrame([wind('2026-05-31 18:00','2026-06-02',25),
                    wind('2026-06-01','2026-06-02',10)])
    obs=observations(['2026-06-01 23:53'],[21])
    cases,diag=comparison_cases(a,b,obs,'ndfd','nbm','wind',offset_hours=-6,obs_time_tolerance='15min')
    assert len(cases)==1 and cases.b_model_value.iloc[0]==25
    assert cases.a_forecast_hour.iloc[0]==24 and cases.b_forecast_hour.iloc[0]==30
    assert cases.actual_offset_hours.iloc[0]==-6
    assert cases.obs_time_offset_minutes.iloc[0]==-7
    scores,sa,sb=comparison_scores(cases,'wind',25)
    assert sa['n']==sb['n']==1 and sa['mae']==1 and sb['mae']==4


def test_lead_filter_only_applies_to_anchor_with_offset():
    a=pd.DataFrame([wind('2026-06-01','2026-06-02',20,ndfd=True)])
    b=pd.DataFrame([wind('2026-05-31 12:00','2026-06-02',25)])
    matched,_=match_forecasts(a,b,'ndfd','nbm','wind',offset_hours=-12,lead_max=24)
    assert len(matched)==1 and matched.b_forecast_hour.iloc[0]==36


def test_no_cartesian_product_and_duplicate_rows_keep_last():
    a=pd.DataFrame([wind('2026-06-01','2026-06-02',10,ndfd=True),wind('2026-06-01','2026-06-02',20,ndfd=True),
                    wind('2026-06-01 06:00','2026-06-02',30,ndfd=True)])
    b=pd.DataFrame([wind('2026-06-01','2026-06-02',21),wind('2026-06-01 06:00','2026-06-02',31)])
    cases,diag=comparison_cases(a,b,observations(['2026-06-02'],[25]),'ndfd','nbm','wind')
    assert len(cases)==2 and diag['a_duplicate_rows']==1
    assert cases.a_model_value.tolist()==[20,30]
    assert cases.obs_value.tolist()==[25,25]


def test_reference_tolerance_is_separate_from_observation_tolerance():
    a=pd.DataFrame([wind('2026-06-01','2026-06-01 06:00',10,ndfd=True)])
    b=pd.DataFrame([wind('2026-06-01 01:00','2026-06-01 06:00',11)])
    matched,d=match_forecasts(a,b,'ndfd','nbm','wind',reference_tolerance='0h')
    assert matched.empty and d['a_unmatched']==1
    matched,_=match_forecasts(a,b,'ndfd','nbm','wind',reference_tolerance='1h')
    assert matched.reference_error_hours.iloc[0]==1
    cases,d=comparison_cases(a,b,observations(['2026-06-01 05:53'],[12]),'ndfd','nbm','wind',
        reference_tolerance='1h',obs_time_tolerance='6min')
    assert cases.empty and d['missing_observations']==1


def test_distinct_stations_targets_do_not_match():
    a=pd.DataFrame([wind('2026-06-01','2026-06-02',10,ndfd=True)])
    for row in [wind('2026-06-01','2026-06-02',11,station='B'),wind('2026-06-01','2026-06-02 06:00',11)]:
        cases,_=match_forecasts(a,pd.DataFrame([row]),'ndfd','nbm','wind')
        assert cases.empty


def test_cutoff_uses_latest_references_before_each_cutoff():
    a=pd.DataFrame([wind('2026-06-01','2026-06-02',10,ndfd=True),wind('2026-06-01 06:00','2026-06-02',20,ndfd=True),
                    wind('2026-06-01 12:00','2026-06-02',30,ndfd=True)])
    b=pd.DataFrame([wind('2026-05-31 18:00','2026-06-02',11),wind('2026-06-01','2026-06-02',21),
                    wind('2026-06-01 06:00','2026-06-02',31)])
    matched,_=match_forecasts(a,b,'ndfd','nbm','wind',matching='cutoff',cutoff='2026-06-01 06:00',offset_hours=-6)
    assert len(matched)==1 and matched.a_model_value.iloc[0]==20 and matched.b_model_value.iloc[0]==21


def probabilistic_wind(init,valid,value,missing=False):
    row=wind(init,valid,value)
    for p in [5,10,25,50,75,90,95]:row[f'wind_p{p}']=np.nan if missing else value
    return row


def test_probability_scores_use_common_valid_sample():
    a=pd.DataFrame([probabilistic_wind('2026-06-01','2026-06-02',10),probabilistic_wind('2026-06-01','2026-06-02',30,False)])
    a.loc[1,'station_id']='B'
    b=a.copy();b['wind_p5']=b['wind_p10']=b['wind_p25']=np.nan
    b.loc[1,['wind_p75','wind_p90','wind_p95']]=np.nan  # only p50 remains for this case
    obs=observations(['2026-06-02']*2,[10,30],['A','B'])
    cases,_=comparison_cases(a,b,obs,'nbmqmd','nbmqmd_exp','wind','50','50')
    table,sa,sb=comparison_scores(cases,'wind',25,probability_a=True,probability_b=True)
    assert len(cases)==2 and sa['n']==sb['n']==2
    assert sa['n_prob']==sb['n_prob']==1
    assert 'brier_score' in table.metric.tolist()
    single,_,single_b=comparison_scores(cases,'wind',25,probability_a=True,probability_b=False)
    assert 'brier_score' not in single.metric.tolist() and 'brier_score' not in single_b


def test_requested_percentile_does_not_silently_fallback():
    row=wind('2026-06-01','2026-06-02',10);row['wind_p75']=20
    with pytest.raises(ValueError,match='requested p50'):
        prepare_forecasts(pd.DataFrame([row]),'nbmqmd','wind','50')


def test_accumulation_window_duration_and_offset():
    a=pd.DataFrame({'station_id':['A'],'valid_time':pd.to_datetime(['2026-06-02 06:00']),
        'forecast_hour':[30],'precip6hr':[.5]})
    b=pd.DataFrame({'station_id':['A'],'valid_time':a.valid_time,'init_time':pd.to_datetime(['2026-05-31 18:00']),
        'qpf_p50':[.4]})
    end=pd.to_datetime(['2026-06-02 05:53','2026-06-02 06:00'])
    obs=pd.DataFrame({'stid':['A','A'],'valid_time':end,'end_time':end,
        'start_time':[end[0]-pd.Timedelta(hours=6),end[1]-pd.Timedelta(hours=24)],'precip_total':[.6,5.]})
    cases,_=comparison_cases(a,b,obs,'ndfd','nbmqmd','precip6hr',None,'50',offset_hours=-6)
    assert cases.obs_value.iloc[0]==.6 and cases.obs_time_offset_minutes.iloc[0]==-7


def test_daily_temperature_preserves_configured_anchor_date():
    a=pd.DataFrame({'station_id':['A'],'valid_time':pd.to_datetime(['2026-06-02 18:00']),
        'forecast_hour':[42],'maxt':[65.]})
    b=pd.DataFrame({'station_id':['A'],'valid_time':pd.to_datetime(['2026-06-02 12:00']),
        'init_time':pd.to_datetime(['2026-06-01']),'maxt_p50':[60.]})
    obs=pd.DataFrame({'stid':['A','A'],'valid_time':pd.to_datetime(['2026-06-03 06:00']*2),
        'date':pd.to_datetime(['2026-06-02']*2),'tmax':[55,66]})
    cases,_=comparison_cases(a,b,obs,'ndfd','nbmqmd','maxt',None,'50')
    assert len(cases)==1 and cases.obs_value.iloc[0]==66


def test_observed_direction_uses_observation_not_forecast():
    a=pd.DataFrame([wind('2026-06-01','2026-06-02',10,ndfd=True)]);a['wind_dir_deg']=180
    b=pd.DataFrame([wind('2026-06-01','2026-06-02',11)])
    o=observations(['2026-06-02'],[12]);o['wind_dir_deg']=350
    cases,_=comparison_cases(a,b,o,'ndfd','nbm','wind')
    assert cases.observed_direction.iloc[0]==350


def test_comparison_loader_reads_previous_init_month_and_obs_once(tmp_path):
    # Both model files live in May, while the requested valid time is June 1.
    a=pd.DataFrame([wind('2026-05-31 18:00','2026-06-01',10,ndfd=True)])
    b=pd.DataFrame([wind('2026-05-31 12:00','2026-06-01',11)])
    for model,frame in [('ndfd',a),('nbm',b)]:
        path=tmp_path/model/'wind';path.mkdir(parents=True)
        name='2026_05_ndfd_wind_archive.parquet' if model=='ndfd' else '2026_05_archive.parquet'
        frame.to_parquet(path/name,index=False)
    path=tmp_path/'obs'/'wind';path.mkdir(parents=True)
    observations(['2026-05-31 23:53'],[12]).to_parquet(path/'2026_05_archive.parquet',index=False)
    ma,mb,obs,messages=load_comparison_data(tmp_path,'ndfd','nbm','obs','wind',date(2026,6,1),date(2026,6,1),['A'])
    cases,_=comparison_cases(ma,mb,obs,'ndfd','nbm','wind',offset_hours=-6)
    assert len(cases)==1


def test_scores_winner_orientation_and_no_events():
    from comparison import metric_preference
    assert metric_preference('bias',-5,1)=='B'
    assert metric_preference('csi',.8,.4)=='A'
    assert metric_preference('far',.1,.4)=='A'
    assert metric_preference('frequency_bias',.9,1.4)=='A'
    assert metric_preference('mae',1,1)=='Tie'
    assert metric_preference('mae',np.nan,1)=='Unavailable'


def test_paired_confidence_interval_is_reproducible():
    cases=pd.DataFrame({'target_time':pd.date_range('2026-06-01',periods=6),
        'a_model_value':[1]*6,'b_model_value':[2]*6,'obs_value':[0]*6})
    assert paired_mae_interval(cases)==(-1,-1)
    assert paired_mae_interval(cases.iloc[:2]) is None


def comparison_fixture(tmp_path):
    a=pd.DataFrame([wind('2026-06-01','2026-06-02',20,ndfd=True)])
    b=pd.DataFrame([wind('2026-05-31 18:00','2026-06-02',25)])
    for model,frame,month in [('ndfd',a,'06'),('nbm',b,'05')]:
        folder=tmp_path/model/'wind';folder.mkdir(parents=True)
        frame.to_parquet(folder/f'2026_{month}_archive.parquet',index=False)
    for model,value in [('nbmqmd',25),('nbmqmd_exp',22)]:
        folder=tmp_path/model/'wind';folder.mkdir(parents=True)
        pd.DataFrame([probabilistic_wind('2026-05-31 18:00','2026-06-02',value)]).to_parquet(
            folder/'2026_05_archive.parquet',index=False)
    folder=tmp_path/'obs'/'wind';folder.mkdir(parents=True)
    observations(['2026-06-01 23:53'],[21]).to_parquet(folder/'2026_06_archive.parquet',index=False)
    metadata=tmp_path/'stations.parquet'
    pd.DataFrame({'station_id':['A'],'latitude':[58.3],'longitude':[-134.5],'name':['Test']}).to_parquet(metadata,index=False)
    return metadata


def test_streamlit_comparison_offset_and_saved_context(tmp_path):
    from streamlit.testing.v1 import AppTest
    metadata=comparison_fixture(tmp_path)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/pages/4_Model_Comparison.py')).run()
    assert not app.exception
    app.text_input(key='compare_archive_root').set_value(str(tmp_path))
    app.text_input(key='compare_metadata').set_value(str(metadata))
    app.text_input(key='compare_stations').set_value('A')
    app.date_input(key='compare_start').set_value(date(2026,6,2))
    app.date_input(key='compare_end').set_value(date(2026,6,2))
    app.number_input(key='compare_obs_tolerance').set_value(15)
    app.checkbox(key='compare_use_offset').set_value(True).run()
    app.number_input(key='compare_offset').set_value(-6.)
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception
    assert not app.error, [e.value for e in app.error]
    result=app.session_state['comparison_result']
    assert len(result['cases'])==1
    assert result['cases'].actual_offset_hours.iloc[0]==-6
    assert result['summary_a']['mae']==1 and result['summary_b']['mae']==4
    app.number_input(key='compare_min_cases').set_value(1).run()
    assert not app.exception
    assert not any(widget.key == 'compare_matching' for widget in app.radio)
    assert not any(widget.key == 'compare_cutoff' for widget in app.text_input)
    assert not any('NDFD reference time is reconstructed' in item.value for item in app.info)
    # A missing run should produce a clear empty-result diagnostic rather than borrowing another cycle.
    app.number_input(key='compare_offset').set_value(-12.).run()
    assert any('previous settings' in i.value for i in app.info)
    assert len(app.session_state['comparison_result']['cases'])==1
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and app.session_state['comparison_result']['cases'].empty


def test_streamlit_mixed_and_two_probabilistic_models(tmp_path):
    from streamlit.testing.v1 import AppTest
    comparison_fixture(tmp_path)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/pages/4_Model_Comparison.py')).run()
    app.text_input(key='compare_archive_root').set_value(str(tmp_path))
    app.text_input(key='compare_stations').set_value('A')
    app.date_input(key='compare_start').set_value(date(2026,6,2))
    app.date_input(key='compare_end').set_value(date(2026,6,2))
    app.selectbox(key='compare_model_b').set_value('nbmqmd')
    app.checkbox(key='compare_use_offset').set_value(True).run()
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error
    result=app.session_state['comparison_result']
    assert 'brier_score' in result['summary_b'] and 'brier_score' not in result['scores'].metric.tolist()
    assert any('Only one model' in i.value for i in app.info)
    app.selectbox(key='compare_model_a').set_value('nbmqmd_exp')
    app.checkbox(key='compare_use_offset').set_value(False).run()
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error
    result=app.session_state['comparison_result']
    assert result['summary_a']['n_prob']==result['summary_b']['n_prob']==1
    assert 'brier_score' in result['scores'].metric.tolist()
    # Comparing two runs/percentiles of the same model must have unique A/B labels.
    app.selectbox(key='compare_model_b').set_value('nbmqmd_exp').run()
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error


def test_gust_observations_can_come_from_wind_archive(tmp_path):
    valid=pd.Timestamp('2026-06-02')
    for model in ['ndfd','nbmqmd']:
        folder=tmp_path/model/'gust';folder.mkdir(parents=True)
        row=dict(station_id='A',valid_time=valid,forecast_hour=24,wind_gust_kt=35,init_time=valid-pd.Timedelta(hours=24))
        for p in [5,10,25,50,75,90,95]:row[f'gust_p{p}']=35
        pd.DataFrame([row]).to_parquet(folder/'2026_06_archive.parquet',index=False)
    folder=tmp_path/'obs'/'wind';folder.mkdir(parents=True)
    pd.DataFrame({'stid':['A'],'valid_time':[valid-pd.Timedelta(minutes=7)],'obs_wind_gust_kts':[37.]}).to_parquet(folder/'2026_06_archive.parquet',index=False)
    a,b,o,messages=load_comparison_data(tmp_path,'ndfd','nbmqmd','obs','gust',date(2026,6,2),date(2026,6,2),['A'])
    cases,_=comparison_cases(a,b,o,'ndfd','nbmqmd','gust',None,'50')
    assert len(cases)==1 and cases.obs_value.iloc[0]==37
    assert any('gust columns from the wind' in m for m in messages)


def test_empty_condition_groups_do_not_break_charts():
    from comparison_plots import plot_group_scores
    import matplotlib.pyplot as plt
    frame=pd.DataFrame({'condition':pd.Series(dtype='object')})
    table=grouped_scores(frame,'condition','wind',25)
    fig=plot_group_scores(table,'condition','mae','A','B','Observed category')
    assert len(fig.axes)==1
    plt.close(fig)
