"""Quantile boxes use archived bounds and the actual matched observations."""
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]/'web_app'))
from config import get_percentile_columns
from station_distribution import plot_station_distribution


def cases(element):
    times = pd.date_range('2026-06-25', periods=3, freq='6h')
    data = pd.DataFrame(dict(station_id=['A']*3, init_time=pd.Timestamp('2026-06-24'),
        target_time=times, valid_time=times, forecast_hour=[24,30,36],
        obs_value=[0., 100., np.nan], distribution_valid=True))
    for level, column in get_percentile_columns(element).items():
        data[column] = float(level)
    return data


@pytest.mark.parametrize('element',['wind','gust','rh','maxt','mint','precip6hr','precip24hr'])
def test_exact_quantile_geometry_and_matched_points(element):
    data=cases(element)
    fig=plot_station_distribution(data,'A','nbmqmd',element,32)
    ax=fig.axes[0]
    assert len(ax.patches)==3
    np.testing.assert_array_equal(np.unique(ax.patches[0].get_path().vertices[:,1]),[25,75])
    np.testing.assert_array_equal(ax.lines[0].get_ydata(),[25,5])
    np.testing.assert_array_equal(ax.lines[1].get_ydata(),[75,95])
    assert any(np.array_equal(line.get_ydata(),[50,50]) for line in ax.lines)
    np.testing.assert_array_equal(ax.collections[0].get_offsets(),[[0,0],[1,100]])
    assert 'p5–p95 whiskers' in [t.get_text() for t in ax.get_legend().get_texts()]
    plt.close(fig)


def test_ties_missing_bounds_and_invalid_distributions_keep_observations():
    data=cases('wind')
    cols=get_percentile_columns('wind')
    data.loc[0,list(cols.values())]=0  # Valid dry/calm degenerate distribution.
    data.loc[1,cols['5']]=np.nan
    data.loc[2,'distribution_valid']=False
    data['obs_value']=[0,1,2]
    fig=plot_station_distribution(data,'A','nbmqmd','wind',25)
    assert len(fig.axes[0].patches)==1
    assert len(fig.axes[0].collections[0].get_offsets())==3
    assert '2 period(s)' in fig.axes[0].texts[0].get_text()
    plt.close(fig)
    data=data.drop(columns=cols['25'])
    fig=plot_station_distribution(data,'A','nbmqmd','wind',25)
    assert not fig.axes[0].patches
    plt.close(fig)


@pytest.mark.parametrize('element',['maxt','mint','precip6hr','precip24hr'])
def test_window_strip_retains_actual_measurement_periods(element):
    data=cases(element)
    data['obs_window_end']=data.valid_time-pd.Timedelta(minutes=7)
    data['obs_window_start']=data.obs_window_end-pd.Timedelta(hours=24)
    if element.startswith('precip'):
        data['model_window_end']=data.valid_time
        data['model_window_start']=data.valid_time-pd.Timedelta(hours=24)
    fig=plot_station_distribution(data,'A','nbmqmd',element,32)
    assert len(fig.axes)==2
    assert 'windows (UTC)' in fig.axes[1].get_xlabel()
    assert len(fig.axes[1].collections)==(2 if element.startswith('precip') else 1)
    plt.close(fig)


def test_empty_station_and_single_period_without_observations():
    data=cases('wind')
    assert plot_station_distribution(data,'B','nbmqmd','wind',25) is None
    data=data.iloc[[0]].assign(obs_value=np.nan)
    fig=plot_station_distribution(data,'A','nbmqmd','wind',25)
    assert len(fig.axes[0].patches)==1
    assert len(fig.axes[0].collections[0].get_offsets())==0
    plt.close(fig)
