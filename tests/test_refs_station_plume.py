"""REFS boxes on a real UTC axis with all requested reports, not only matches."""
from datetime import date
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from station_observations import report_series
from station_distribution import plot_station_distribution
from storm_comparison import plot_comparison_station,compare_storm_runs
from test_station_distribution import cases


def reports(element='wind'):
    times=pd.date_range('2026-06-24 23:53',periods=27,freq='h',tz='UTC')
    values=np.arange(len(times),dtype=float)
    values[3]=np.nan;values[4]=np.inf;values[5]=0.
    column='obs_wind_speed_kts' if element=='wind' else 'obs_wind_gust_kts'
    a=pd.DataFrame(dict(stid='A',valid_time=times,**{column:values}))
    return pd.concat([a,a.assign(stid='OTHER')],ignore_index=True)


@pytest.mark.parametrize('element',['wind','gust'])
def test_every_finite_report_inclusive_end_day_and_actual_timestamps(element):
    raw=reports(element)
    series=report_series(raw,'A',element,date(2026,6,25),date(2026,6,25))
    assert len(series)==22
    assert series.report_time.min()==pd.Timestamp('2026-06-25 00:53')
    assert series.report_time.max()==pd.Timestamp('2026-06-25 23:53')
    assert series.observed_value.eq(0).any()
    c=cases(element)
    c['obs_valid_time']=c.target_time-pd.Timedelta(minutes=7)
    figure=plot_station_distribution(c,'A','refs',element,25,observations=raw,
        plot_start=date(2026,6,25),plot_end=date(2026,6,25))
    ax=figure.axes[0]
    all_reports=next(x for x in ax.collections if x.get_label()=='All observed reports (actual times)')
    np.testing.assert_allclose(all_reports.get_offsets()[:,0],mdates.date2num(series.report_time))
    assert len(all_reports.get_offsets())==22 and len(ax.patches)==3
    centers=[np.mean(np.unique(box.get_path().vertices[:,0])) for box in ax.patches]
    np.testing.assert_allclose(centers,mdates.date2num(c.target_time))
    expected=mdates.date2num([pd.Timestamp('2026-06-25'),pd.Timestamp('2026-06-26')])
    assert ax.get_xlim()[0]<expected[0] and np.isclose(ax.get_xlim()[1],expected[1])
    plt.close(figure)


def test_irregular_forecast_spacing_missing_observations_and_no_input_mutation():
    c=cases('wind');c.loc[2,'target_time']+=pd.Timedelta(hours=6)
    before=c.copy(deep=True)
    figure=plot_station_distribution(c,'A','refs','wind',25,observations=pd.DataFrame(),
        plot_start=date(2026,6,25),plot_end=date(2026,6,25))
    centers=[np.mean(np.unique(box.get_path().vertices[:,0])) for box in figure.axes[0].patches]
    assert np.isclose(centers[2]-centers[1],2*(centers[1]-centers[0]))
    pd.testing.assert_frame_equal(c,before)
    plt.close(figure)


@pytest.mark.parametrize('refs_side',['a','b'])
def test_comparison_overlay_keeps_all_reports_and_shared_cases(refs_side):
    c=cases('wind');q=c.drop(columns=['obs_value','distribution_valid','target_time'])
    deterministic=q[['station_id','init_time','valid_time','forecast_hour']].assign(wind_speed_kt=20.)
    raw=reports()
    a,b,ma,mb,pa,pb=(q,deterministic,'refs','rrfs','50',None) if refs_side=='a' else (deterministic,q,'rrfs','refs',None,'50')
    shared,_=compare_storm_runs(a,b,raw,ma,mb,'wind',c.init_time.iloc[0],pa,pb)
    before=shared.copy(deep=True)
    fig=plot_comparison_station(shared,'A',ma,mb,'wind',pa,pb,25,observations=raw,
        plot_start=date(2026,6,25),plot_end=date(2026,6,25))
    cloud=next(x for x in fig.axes[0].collections if x.get_label()=='All observed reports (actual times)')
    assert len(cloud.get_offsets())==22 and len(cloud.get_offsets())>len(shared)
    pd.testing.assert_frame_equal(shared,before)
    plt.close(fig)


def test_refs_page_passes_full_observations_and_requested_bounds(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import storm_visuals,station_distribution
    from test_rrfs_refs import fixture
    root,derived,init,meta=fixture(tmp_path,'wind',custom=True)
    # Add reports between forecasts to the source archive itself.
    folder=root/'obs/wind'
    path=folder/'2026_10_archive.parquet'
    obs=pd.read_parquet(path)
    extra=obs.iloc[[0]].copy();extra['valid_time']+=pd.Timedelta(minutes=30)
    pd.concat([obs,extra],ignore_index=True).to_parquet(path,index=False)
    calls=[]
    original=station_distribution.plot_station_distribution
    def capture(*args,**kwargs):
        calls.append(kwargs)
        return original(*args,**kwargs)
    monkeypatch.setattr(station_distribution,'plot_station_distribution',capture)
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kwargs:None)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20).run()
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.secrets.setdefault('local',{})['archive_root']=str(root)
    app.secrets.setdefault('local',{})['metadata_path']=str(meta)
    app.selectbox(key='storm_Model').set_value('refs').run()
    app.secrets.setdefault('local',{})['refs_root']=str(derived)
    _selected_init=pd.Timestamp(str(init))
    app.date_input(key='storm_init_date').set_value(_selected_init.date())
    app.selectbox(key='storm_init_hour').set_value(_selected_init.hour)
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,10,1))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,10,3))
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error,[x.value for x in app.exception]+[x.value for x in app.error]
    assert calls and len(calls[-1]['observations'])>len(app.session_state['storm_result']['cases'])
    assert calls[-1]['style']=='plume'
    assert calls[-1]['plot_start']==date(2026,10,1) and calls[-1]['plot_end']==date(2026,10,3)
    assert any('Small red points show every available report' in x.value for x in app.caption)
