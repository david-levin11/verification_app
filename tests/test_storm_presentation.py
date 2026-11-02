"""Shaded quantile plumes and source-specific initialization date/hour controls."""
from datetime import date
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from storm_initialization import initialization_hours
from station_distribution import plot_station_distribution
from storm_comparison import plot_comparison_station,compare_storm_runs
from test_station_distribution import cases
from test_refs_station_plume import reports


@pytest.mark.parametrize('model,element,hours',[
    ('nbm','wind',[1,7,13,19]),('nbm','gust',[1,7,13,19]),('nbm_exp','wind',[1,7,13,19]),
    ('nbmqmd','wind',[0,6,12,18]),('nbmqmd_exp','gust',[0,6,12,18]),
    ('hrrr','wind',[0,6,12,18]),('rrfs','rh',[0,6,12,18]),('refs','precip6hr',[0,6,12,18]),
    ('nbm','maxt',[0,6,12,18]),('nbm','mint',[0,6,12,18]),
    ('nbm','precip6hr',[0,6,12,18]),('nbm','precip24hr',[0,6,12,18]),
    ('urma','wind',list(range(0,24,3))),('ndfd','wind',list(range(24)))])
def test_initialization_hours_match_archiver_source_rules(model,element,hours):
    assert initialization_hours(model,element)==hours


@pytest.mark.parametrize('model',['refs','nbmqmd'])
@pytest.mark.parametrize('element',['wind','gust','rh','precip6hr'])
def test_shaded_plume_bounds_and_median_use_archived_quantiles(model,element):
    c=cases(element)
    fig=plot_station_distribution(c,'A',model,element,25,style='plume')
    ax=fig.axes[0]
    assert not ax.patches
    bands=[x for x in ax.collections if isinstance(x,PolyCollection)]
    assert len(bands)==2
    np.testing.assert_array_equal(np.unique(bands[0].get_paths()[0].vertices[:,1]),[5,95])
    np.testing.assert_array_equal(np.unique(bands[1].get_paths()[0].vertices[:,1]),[25,75])
    assert next(line for line in ax.lines if line.get_label()=='p50 median').get_ydata().tolist()==[50,50,50]
    plt.close(fig)


def test_invalid_quantile_rows_break_shading_and_all_reports_remain():
    c=cases('wind');c.loc[1,'distribution_valid']=False
    fig=plot_station_distribution(c,'A','refs','wind',25,style='plume',observations=reports(),
        plot_start=date(2026,6,25),plot_end=date(2026,6,25))
    line=next(line for line in fig.axes[0].lines if line.get_label()=='p50 median')
    assert np.isnan(line.get_ydata()[1])
    band=next(x for x in fig.axes[0].collections if x.get_label()=='p5–p95')
    assert len(band.get_paths())==2
    assert len(next(x for x in fig.axes[0].collections if x.get_label()=='All observed reports (actual times)').get_offsets())==22
    plt.close(fig)


def test_comparison_plumes_share_colors_and_keep_observation_markers():
    c=cases('wind');q=c.drop(columns=['obs_value','distribution_valid','target_time'])
    shared,_=compare_storm_runs(q,q,reports(),'refs','nbmqmd','wind',c.init_time.iloc[0],'50','50')
    fig=plot_comparison_station(shared,'A','refs','nbmqmd','wind','50','50',25,style='plume',
        observations=reports(),plot_start=date(2026,6,25),plot_end=date(2026,6,25))
    assert not fig.axes[0].patches
    assert len([x for x in fig.axes[0].collections if isinstance(x,PolyCollection)])==4
    assert len(next(x for x in fig.axes[0].collections if x.get_label()=='All observed reports (actual times)').get_offsets())==22
    plt.close(fig)


def test_calendar_and_hour_change_models_without_changing_dates():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20).run()
    app.switch_page('pages/3_Storm_Zoom.py').run()
    assert not any(x.label.startswith('Model Init Time') for x in app.text_input)
    app.date_input(key='storm_init_date').set_value(date(2026,10,31))
    assert app.selectbox(key='storm_init_hour').options==['01Z','07Z','13Z','19Z']
    app.selectbox(key='storm_init_hour').set_value(7).run()
    app.selectbox(key='storm_Model').set_value('hrrr').run()
    assert app.date_input(key='storm_init_date').value==date(2026,10,31)
    assert app.selectbox(key='storm_init_hour').options==['00Z','06Z','12Z','18Z']
    assert app.selectbox(key='storm_init_hour').value in [0,6,12,18]
    app.selectbox(key='storm_Model').set_value('nbm').run()
    app.selectbox(key='storm_Element').set_value('maxt').run()
    assert app.selectbox(key='storm_init_hour').options==['00Z','06Z','12Z','18Z']
    assert not app.exception
