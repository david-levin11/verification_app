"""NBM scalar fields run through all verification pages without quantile columns."""
from datetime import date
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt

ROOT=Path(__file__).parents[1]/'web_app'
sys.path.insert(0,str(ROOT))
from config import is_probabilistic,get_available_elements,get_percentile_columns
from comparison import prepare_forecasts,comparison_cases,comparison_scores
from storm_analysis import build_storm_cases
from accumulation_storm import plot_accumulation_periods
from pairing import build_verification_pairs

FIELDS=['wind','maxt','mint','precip6hr','precip24hr']


def deterministic_frames(element):
    rows=[];obs=[]
    daily=element in ['maxt','mint']
    duration=6 if element=='precip6hr' else 24
    init=pd.Timestamp('2026-06-29 01:00' if element=='wind' else '2026-06-29')
    for station,offset in [('A',0),('B',1)]:
        for number in range(2):
            target=pd.Timestamp('2026-06-30')+pd.Timedelta(days=number)
            if daily:
                start=target+pd.Timedelta(hours=12 if element=='maxt' else 0)
                valid=start+pd.Timedelta(hours=18)
                value=[-10.,0.][number]+offset
                observation=dict(stid=station,date=target,window_start=start,window_end=valid,
                    **{('tmax' if element=='maxt' else 'tmin'):value})
            else:
                valid=(pd.Timestamp('2026-06-30 06:00')+pd.Timedelta(hours=number*6) if element!='precip24hr' else target)
                value=([0.,10.][number] if element=='wind' else [0.,2.][number])+offset
                end=valid-pd.Timedelta(minutes=7)
                observation=dict(stid=station,valid_time=end)
                if element=='wind':observation['obs_wind_speed_kts']=value
                else:observation.update(start_time=end-pd.Timedelta(hours=duration),end_time=end,precip_total=value)
            row=dict(station_id=station,init_time=init,valid_time=valid,forecast_hour=(valid-init).total_seconds()/3600,
                **{('wind_speed_kt' if element=='wind' else element):value})
            rows.append(row);obs.append(observation)
    m,o=pd.DataFrame(rows),pd.DataFrame(obs)
    q=m.drop(columns='wind_speed_kt' if element=='wind' else element).copy()
    q['init_time']=pd.Timestamp('2026-06-29')
    q['forecast_hour']=(q.valid_time-q.init_time).dt.total_seconds()/3600
    for p,col in get_percentile_columns(element).items():
        value=m['wind_speed_kt' if element=='wind' else element]+(float(p)-50)/100
        q[col]=value if daily else value.clip(lower=0)
    return m,o,q


def archive_fixture(root,element):
    m,o,q=deterministic_frames(element)
    for name,frame in [('nbm',m),('nbmqmd',q),('obs',o)]:
        folder=root/name/element;folder.mkdir(parents=True,exist_ok=True)
        times=(frame.date if 'date' in frame else frame.valid_time) if name=='obs' else frame.init_time
        for month,chunk in frame.groupby(times.dt.strftime('%Y_%m')):
            chunk.to_parquet(folder/f'{month}_archive.parquet',index=False)
    from test_storm_analysis import metadata
    p=root/'metadata.parquet';metadata().to_parquet(p,index=False)
    return m,o,q,p


@pytest.mark.parametrize('element',FIELDS)
def test_scalar_nbm_values_and_mixed_probability_comparison(element):
    m,o,q=deterministic_frames(element)
    assert element in get_available_elements('nbm') and not is_probabilistic('nbm',element)
    assert is_probabilistic('nbmqmd',element)
    # Even a legacy quantile column must not replace the requested scalar field.
    m[get_percentile_columns(element)['50']]=999.
    prepared=prepare_forecasts(m,'nbm',element,'50')
    np.testing.assert_array_equal(prepared.model_value,m['wind_speed_kt' if element=='wind' else element])
    o['valid_time']=o.window_end if 'window_end' in o else o.valid_time
    pairs=build_verification_pairs(m,o,'nbm','obs',element)
    assert len(pairs)==4 and pairs.model_value.eq(pairs.obs_value).all()
    for a,b,ma,mb,pa,pb,proba,probb in [(m,q,'nbm','nbmqmd',None,'50',False,True),
            (q,m,'nbmqmd','nbm','50',None,True,False), (m,m,'nbm','nbm',None,None,False,False)]:
        cases,_=comparison_cases(a,b,o,ma,mb,element,pa,pb,reference_tolerance='1h',lead_max=168)
        _,sa,sb=comparison_scores(cases,element,1,probability_a=proba,probability_b=probb)
        assert len(cases)==4 and sa['mae']==sb['mae']==0
        assert sa.get('n_prob',0)==(4 if proba else 0)
        assert sb.get('n_prob',0)==(4 if probb else 0)


@pytest.mark.parametrize('element',FIELDS)
def test_nbm_runs_all_four_pages_without_percentile_controls(tmp_path,monkeypatch,element):
    from streamlit.testing.v1 import AppTest
    import storm_visuals
    m,o,q,meta=archive_fixture(tmp_path,element)
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kwargs:None)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    for page,button,result in [('map','Build Station Metric Map','station_metrics'),
            ('aggregate','Run Aggregate Verification','aggregate_summary')]:
        app.switch_page('pages/1_Map_Explorer.py' if page=='map' else 'pages/2_Aggregate_Verification.py').run()
        if page=='map':app.text_input(key='map_metadata_path').set_value(str(meta)).run()
        else:app.text_input(key='aggregate_station_ids_input').set_value('A,B')
        app.text_input(key=f'{page}_ui_archive_root').set_value(str(tmp_path))
        app.selectbox(key=f'{page}_ui_model').set_value('nbm').run()
        app.selectbox(key=f'{page}_ui_element').set_value(element).run()
        assert not any(s.label=='Verification Percentile' for s in app.selectbox)
        app.date_input(key=f'{page}_ui_start_date').set_value(date(2026,6,30))
        app.date_input(key=f'{page}_ui_end_date').set_value(date(2026,7,1))
        app.checkbox(key=f'{page}_ui_use_all_forecast_hours').set_value(True).run()
        next(b for b in app.button if b.label==button).click().run(timeout=30)
        assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
        score=app.session_state[result]
        assert (score.n.sum() if page=='map' else score['n'])==4
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.text_input(key='storm_Local Archive Root').set_value(str(tmp_path))
    app.text_input(key='storm_metadata').set_value(str(meta))
    app.selectbox(key='storm_Model').set_value('nbm').run()
    app.selectbox(key='storm_Element').set_value(element).run()
    assert not any(s.label=='Verification Percentile' for s in app.selectbox)
    app.text_input(key='storm_Model Init Time (YYYY-MM-DD HH:MM:SS)').set_value(str(m.init_time.iloc[0]))
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,6,30))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,7,1))
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
    cases=app.session_state['storm_result']['cases']
    assert len(cases)==4 and cases.obs_value.notna().all()
    assert 'forecast_probability' not in cases and 'observed_percentile' not in cases
    assert set(app.selectbox(key=f'storm_map_display_{element}_False').options)=={'Forecast','Observation','Signed error','Absolute error'}
    app.switch_page('pages/4_Model_Comparison.py').run()
    app.text_input(key='compare_archive_root').set_value(str(tmp_path))
    app.text_input(key='compare_stations').set_value('A,B')
    app.selectbox(key='compare_model_a').set_value('nbmqmd').run()
    app.selectbox(key='compare_model_b').set_value('nbm').run()
    app.selectbox(key='compare_element').set_value(element).run()
    assert not any(s.label=='Model B point percentile' for s in app.selectbox)
    app.selectbox(key=f'compare_pct_a_{element}').set_value('50')
    app.date_input(key='compare_start').set_value(date(2026,6,30))
    app.date_input(key='compare_end').set_value(date(2026,7,1))
    app.number_input(key='compare_lead_max').set_value(168)
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
    result=app.session_state['comparison_result']
    assert len(result['cases'])==4 and result['summary_a']['n_prob']==4
    assert result['summary_b'].get('n_prob',0)==0


@pytest.mark.parametrize('element',['precip6hr','precip24hr'])
def test_accumulation_storm_windows_zeros_missing_obs_and_duration_filter(element):
    m,o,q=deterministic_frames(element)
    # Wrong-duration report exactly at the endpoint must not hide the valid -7min one.
    wrong=o.iloc[[0]].copy();wrong['end_time']=m.valid_time.iloc[0];wrong['valid_time']=wrong.end_time
    wrong['start_time']=wrong.end_time-pd.Timedelta(hours=48);wrong['precip_total']=999
    o=pd.concat([o,wrong],ignore_index=True)
    c=build_storm_cases(m,o,'nbm','obs',element,m.init_time.iloc[0],tolerance='15min')
    assert len(c)==4 and c.model_value.eq(c.obs_value).all()
    assert c.obs_time_offset_minutes.eq(-7).all()
    hours=6 if element=='precip6hr' else 24
    assert (c.model_window_end-c.model_window_start).eq(pd.Timedelta(hours=hours)).all()
    assert (c.obs_window_end-c.obs_window_start).eq(pd.Timedelta(hours=hours)).all()
    for frame in [c,build_storm_cases(m,o.iloc[0:0],'nbm','obs',element,m.init_time.iloc[0])]:
        fig=plot_accumulation_periods(frame,'A','nbm',element)
        assert 'Accumulation windows' in fig.axes[0].get_xlabel()
        assert 'in' in fig.axes[0].get_ylabel()
        forecast=next(line for line in fig.axes[0].lines if line.get_label()=='NBM forecast')
        assert forecast.get_ydata()[0]==0
        plt.close(fig)
    probabilistic=build_storm_cases(q,o,'nbmqmd','obs',element,q.init_time.iloc[0],'50')
    fig=plot_accumulation_periods(probabilistic,'A','nbmqmd',element,'50')
    assert any('p25–p75'==collection.get_label() for collection in fig.axes[0].collections)
    plt.close(fig)
