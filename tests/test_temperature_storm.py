"""Temperature storm matching reuses the shared date convention, including window boundaries."""
from datetime import date
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt

ROOT=Path(__file__).parents[1]/'web_app'
sys.path.insert(0,str(ROOT))
from storm_analysis import build_storm_cases,evolution_summary
from comparison import comparison_cases
from data_loader import fetch_data
from config import get_percentile_columns
from storm_visuals import map_description,plot_evolution,snapshot_map_data
from temperature_storm import plot_temperature_periods,temperature_snapshot_label


def temperature_frames(element='maxt',probabilistic=True):
    rows=[];reports=[]
    for station,adjust in [('A',0),('B',5)]:
        for day in ['2026-06-30','2026-07-01']:
            target=pd.Timestamp(day)
            valid=target+pd.Timedelta(hours=12 if probabilistic else 0)
            init=pd.Timestamp('2026-06-29')
            row=dict(station_id=station,init_time=init,valid_time=valid,
                     forecast_hour=(valid-init).total_seconds()/3600)
            if probabilistic:
                for p,column in get_percentile_columns(element).items():row[column]=float(p)-50+adjust
            else:row[element]=adjust
            rows.append(row)
            start=target+pd.Timedelta(hours=12 if element=='maxt' else 0)
            reports.append(dict(stid=station,date=target,window_start=start,
                window_end=start+pd.Timedelta(hours=18),temp_units='F',
                **{('tmax' if element=='maxt' else 'tmin'):float(adjust)}))
    return pd.DataFrame(rows),pd.DataFrame(reports)


@pytest.mark.parametrize('element',['maxt','mint'])
def test_storm_and_comparison_use_identical_date_matches(element):
    a,o=temperature_frames(element,False)
    b,_=temperature_frames(element,True)
    a=a.drop(columns='init_time')  # NDFD uses the shared reference reconstruction.
    storm=build_storm_cases(b,o,'nbmqmd','obs',element,'2026-06-29','50',tolerance='0min')
    # Comparison loader standardizes valid_time from window_end before pairing.
    reports=o.assign(valid_time=o.window_end)
    compared,_=comparison_cases(a,b,reports,'ndfd','nbmqmd',element,None,'50',
        reference_tolerance='0h',obs_time_tolerance='0min')
    assert len(storm)==len(compared)==4
    assert storm.obs_value.tolist()==compared.sort_values(['target_time','station_id']).obs_value.tolist()
    assert storm.obs_window_start.notna().all() and storm.obs_window_end.notna().all()
    assert storm.forecast_date.dt.hour.eq(0).all()
    assert 'obs_time_offset_minutes' not in storm
    assert storm.obs_window_end_offset_minutes.notna().all()
    assert 'for 2026-06-30' in temperature_snapshot_label(pd.Timestamp('2026-06-30'),storm,element)


@pytest.mark.parametrize('element',['maxt','mint'])
@pytest.mark.parametrize('probabilistic',[True,False])
def test_temperature_loader_includes_next_day_window_end_and_next_month(element,probabilistic,tmp_path):
    m,o=temperature_frames(element,probabilistic)
    model='nbmqmd' if probabilistic else 'ndfd'
    if model=='ndfd':m=m.drop(columns='init_time')
    folder=tmp_path/model/element;folder.mkdir(parents=True)
    m.to_parquet(folder/'2026_06_archive.parquet',index=False)
    folder=tmp_path/'obs'/element;folder.mkdir(parents=True)
    for month,frame in o.groupby(o.date.dt.month):frame.to_parquet(folder/f'2026_{month:02d}_archive.parquet',index=False)
    loaded,reports,_=fetch_data('Storm Specific Zoom',model,'obs',date(2026,6,30),date(2026,6,30),
        ['A','B'],[],'2026-06-29',{},'50' if probabilistic else None,element=element,
        archive_root=tmp_path,obs_time_tolerance='0min')
    cases=build_storm_cases(loaded,reports,model,'obs',element,'2026-06-29','50' if probabilistic else None,tolerance='0min')
    assert len(cases)==2 and cases.obs_value.notna().all()
    assert cases.forecast_date.eq(pd.Timestamp('2026-06-30')).all()
    if element=='maxt':assert cases.obs_window_end.eq(pd.Timestamp('2026-07-01 06:00')).all()
    figure=plot_temperature_periods(cases,'A',model,element,'50' if probabilistic else None)
    assert len(figure.axes)==2
    assert '°F' in figure.axes[0].get_ylabel()
    assert figure.axes[1].get_xlabel()=='Observed measurement windows (UTC)'
    assert figure.axes[0].lines[0].get_linestyle()=='None'  # Daily values are not instantaneous connecting lines.
    plt.close(figure)


@pytest.mark.parametrize('element',['maxt','mint'])
def test_temperature_negatives_zeros_duplicate_observations_and_cold_threshold(element):
    m,o=temperature_frames(element,True)
    value='tmax' if element=='maxt' else 'tmin'
    o.loc[0,value]=-10.
    later=o.iloc[[1]].copy();later[value]=0
    o=pd.concat([o,later],ignore_index=True)
    c=build_storm_cases(m,o,'nbmqmd','obs',element,'2026-06-29','50',threshold=0,operator='<=')
    assert len(c)==4 and c.obs_value.iloc[0]==-10
    assert c.loc[c.station_id.eq('A') & c.forecast_date.eq(pd.Timestamp('2026-07-01')),'obs_value'].iloc[0]==0
    assert c.forecast_probability.iloc[0]==.5
    assert c.observed_event.eq(1).sum()>=2
    assert evolution_summary(c).valid_time.dt.hour.eq(0).all()
    fig=plot_evolution(evolution_summary(c),[('25','75'),('10','90'),('5','95')],'°F',date_based=True)
    assert fig.axes[-1].get_xlabel()=='Forecast date used for verification'
    plt.close(fig)


def test_daily_duplicates_use_comparison_target_and_missing_windows_remain_unknown():
    m,o=temperature_frames()
    duplicate=m.iloc[[0]].copy();duplicate['valid_time']+=pd.Timedelta(hours=1)
    duplicate['forecast_hour']+=1;duplicate['maxt_p50']=1
    m=pd.concat([m,duplicate],ignore_index=True)
    c=build_storm_cases(m,o.drop(columns=['window_start','window_end']).assign(valid_time=o.date),
        'nbmqmd','obs','maxt','2026-06-29','50')
    assert len(c)==4 and c.obs_window_start.isna().all()
    assert c.loc[c.station_id.eq('A') & c.forecast_date.eq(pd.Timestamp('2026-06-30')),'model_value'].iloc[0]==1
    summary=evolution_summary(c)
    assert np.isnan(summary.forecast_hour.iloc[0])
    assert summary.forecast_hour_min.iloc[0]==36 and summary.forecast_hour_max.iloc[0]==37
    fig=plot_temperature_periods(c,'A','nbmqmd','maxt','50')
    assert len(fig.axes)==1
    plt.close(fig)


def test_subzero_temperature_map_colors_and_bar_limits_cover_negative_values():
    from test_storm_analysis import metadata
    m,o=temperature_frames('mint',False)
    m['mint']=[-30.,-25.,-20.,-15.]
    o['tmin']=[-40.,-35.,-20.,-15.]
    c=build_storm_cases(m,o,'ndfd','obs','mint','2026-06-29')
    snapshot=c[c.forecast_date.eq(pd.Timestamp('2026-06-30'))]
    for metric,low in [('model_value',-30),('obs_value',-40)]:
        data,_,limits=snapshot_map_data(snapshot,metadata(),metric)
        assert limits==(low,0)
        assert len({tuple(color) for color in data.fill_color})==2
        assert data[metric].between(*limits).all()


@pytest.mark.parametrize('element',['maxt','mint'])
@pytest.mark.parametrize('model',['nbmqmd','ndfd'])
def test_temperature_storm_page_period_selector_plots_and_threshold_direction(tmp_path,monkeypatch,element,model):
    from streamlit.testing.v1 import AppTest
    import storm_visuals
    from test_storm_analysis import metadata
    m,o=temperature_frames(element,model=='nbmqmd')
    if model=='ndfd':m=m.drop(columns='init_time')
    folder=tmp_path/model/element;folder.mkdir(parents=True)
    m.to_parquet(folder/'2026_06_archive.parquet',index=False)
    folder=tmp_path/'obs'/element;folder.mkdir(parents=True)
    for month,frame in o.groupby(o.date.dt.month):frame.to_parquet(folder/f'2026_{month:02d}_archive.parquet',index=False)
    path=tmp_path/'metadata.parquet';metadata().to_parquet(path,index=False)
    renders=[]
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kwargs:renders.append(kwargs))
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=15).run()
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.text_input(key='storm_Local Archive Root').set_value(str(tmp_path))
    app.text_input(key='storm_metadata').set_value(str(path))
    app.selectbox(key='storm_Model').set_value(model).run()
    app.selectbox(key='storm_Element').set_value(element).run()
    assert not any(n.label=='Observation tolerance (minutes)' for n in app.number_input)
    assert app.selectbox(key=f'storm_operator_{element}').value==('<=' if element=='mint' else '>=')
    app.text_input(key='storm_Model Init Time (YYYY-MM-DD HH:MM:SS)').set_value('2026-06-29')
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,6,30))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,7,1))
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error,[x.value for x in app.exception]+[x.value for x in app.error]
    c=app.session_state['storm_result']['cases']
    assert len(c)==4 and c.obs_value.notna().all()
    assert any(s.label=='Snapshot forecast date' for s in app.selectbox)
    assert renders and renders[-1]['records'][0]['obs_window_start']
    assert not any('observation tolerance ±' in x.value for x in app.caption)
    assert any('Observed measurement periods' in x.value or 'actual observed measurement periods' in x.value for x in app.caption)
