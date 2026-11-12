"""Display limits preserve values, map semantics and independently saved controls."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / 'web_app'))
from color_scales import (standard_bounds, fit_bounds, clipped_counts,
                          scale_units, colorbar, color_mapping)
from maps import add_map_style_columns
from storm_visuals import snapshot_map_data, map_colorbar
from comparison_plots import station_difference_map


def test_precipitation_outlier_saturates_without_hiding_common_biases_or_values():
    frame = pd.DataFrame({'bias': [-4., -.2, 0., .2, 4.], 'n': [10]*5})
    bounds = standard_bounds('precip6hr', 'bias')
    styled, low, high = add_map_style_columns(frame, 'bias', bounds)
    assert (low, high) == (-.25, .25)
    assert len(set(map(tuple, styled.fill_color))) == 5
    assert styled.metric_value.tolist() == frame.bias.tolist()
    assert clipped_counts(styled.bias, bounds) == (1, 1)
    assert standard_bounds('precip24hr', 'bias') == (-.5, .5)
    assert standard_bounds('mint', 'bias') == (-5., 5.)
    assert scale_units('minrh', 'bias') == 'percentage points'
    assert scale_units('minrh', 'model_value') == '%'


def test_fit_is_robust_zero_based_for_errors_and_symmetric_for_signed_values():
    # An isolated extreme must not hide differences among the other 100 stations.
    values = pd.Series([.1]*50 + [.2]*50 + [100., np.inf, np.nan])
    assert fit_bounds(values, 'mae') == (0., .2)
    assert fit_bounds(values, 'bias') == (-.2, .2)
    assert fit_bounds([-.1, .1], 'mae', difference=True) == (-.1, .1)
    for values in [[], [np.nan, np.inf], [0., 0.], [3., 3.]]:
        low, high = fit_bounds(values, 'mae')
        assert np.isfinite([low, high]).all() and low < high
    assert standard_bounds('wind', 'pod') == (0., 1.)
    assert standard_bounds('wind', 'pod', difference=True) == (-.25, .25)


@pytest.mark.parametrize('metric', ['pod', 'far'])
def test_custom_proportion_limits_control_marker_colors(metric):
    frame = pd.DataFrame({metric: [.25, .5, .75]})
    styled, low, high = add_map_style_columns(frame, metric, (.25, .75))
    assert (low, high) == (.25, .75)
    assert len(set(map(tuple, styled.fill_color))) == 3
    ends = [styled.fill_color.iloc[i][:3] for i in [0, -1]]
    assert ends == ([[44,127,184],[229,245,249]] if metric == 'far'
                    else [[229,245,249],[44,127,184]])


def test_comparison_scale_saturates_and_retains_signed_advantage_and_cases():
    metadata = pd.DataFrame({'station_id': ['A','B','C'], 'latitude': [58.,59.,60.],
                             'longitude': [-135.,-136.,-137.]})
    table = pd.DataFrame({'station_id':['A','B','C'], 'metric':'mae', 'n':20,
                          'a':[.1,.2,4.], 'b':[.2,.1,.1]})
    _, data = station_difference_map(table, metadata, 'mae', 'A', 'B', limits=(-.25,.25))
    assert data.advantage.tolist() == pytest.approx([.1,-.1,-3.9])
    assert data.n.sum() == 60
    assert data.color.iloc[-1][:3] == [179,88,6]
    assert data.color.iloc[0][2] > data.color.iloc[0][0]  # blue favors A
    assert clipped_counts(data.advantage, (-.25,.25)) == (1,0)


def test_storm_custom_limits_bar_and_clipping_use_identical_normalization():
    metadata = pd.DataFrame({'station_id':['A','B','C'], 'latitude':[58.,59.,60.],
                             'longitude':[-135.,-136.,-137.]})
    snap = pd.DataFrame({'station_id':['A','B','C'], 'error':[-2.,0.,2.]})
    data, _, bounds = snapshot_map_data(snap, metadata, 'error', (-.25,.25))
    assert bounds == (-.25,.25) and data.metric_value.tolist() == [-2.,0.,2.]
    fig = map_colorbar('error',bounds,'Error','in',data.error)
    assert fig.axes[0].get_xlim() == bounds
    assert fig.axes[0]._colorbar.extend == 'both'
    plt.close(fig)
    # Probability ticks must not expand a custom zoom of the colorbar.
    fig = map_colorbar('forecast_probability',(.2,.8),'Probability','', [.1,.5,.9])
    assert fig.axes[0].get_xlim() == (.2,.8)
    plt.close(fig)
    fig = colorbar((0,.5), 'MAE (in)', ['white','blue'], [0,.2,4.])
    assert fig.axes[0]._colorbar.extend == 'both'
    plt.close(fig)


def test_scale_controls_custom_fit_invalid_and_independent_element_settings():
    from streamlit.testing.v1 import AppTest
    script = '''
import streamlit as st
from page_controls import PageControls
from color_scales import scale_controls
ui=PageControls('map')
element=ui.selectbox('Element',['precip6hr','mint'],key='element')
metric=ui.selectbox('Metric',['bias','mae'],key='metric')
st.session_state['limits']=scale_controls(ui,[-.1,.2,4.],element,metric)
'''
    app = AppTest.from_string(script).run()
    assert app.session_state['limits'] == (-.25,.25)
    mode = 'map_color_precip6hr_bias_False'
    app.selectbox(key=mode).set_value('Custom').run()
    app.number_input(key=mode+'_bound').set_value(.1).run()
    assert app.session_state['limits'] == (-.1,.1)
    app.selectbox(key='map_element').set_value('mint').run()
    assert app.session_state['limits'] == (-5.,5.)
    app.selectbox(key='map_element').set_value('precip6hr').run()
    assert app.session_state['limits'] == (-.1,.1)
    app.selectbox(key=mode).set_value('Fit to data').run()
    assert app.session_state['limits'] == fit_bounds([-.1,.2,4.],'bias')
    app.selectbox(key='map_metric').set_value('mae').run()
    mode = 'map_color_precip6hr_mae_False'
    app.selectbox(key=mode).set_value('Custom').run()
    app.number_input(key=mode+'_low').set_value(2.).run()
    assert app.error and app.session_state['limits'] == (0.,.5)
    app.number_input(key=mode+'_high').set_value(3.).run()
    assert not app.error and not app.exception
    assert app.session_state['limits'] == (2.,3.)


@pytest.mark.parametrize('metric', ['mae', 'pod', 'far'])
def test_sequential_markers_match_compact_stepped_legend_including_boundaries(metric):
    from maps import show_map_legend
    import maps
    from unittest.mock import patch
    limits = (0., 1.)
    values = [-1., .01, .19, .2, .39, .4, .6, .8, 1., 2.]
    frame = pd.DataFrame({metric: values})
    styled, _, _ = add_map_style_columns(frame, metric, limits)
    captured = []
    with patch.object(maps.st, 'pyplot', side_effect=lambda fig, **kw: captured.append((fig, kw))):
        show_map_legend(frame, metric, limits)
    fig, arguments = captured[0]
    bar = fig.axes[0]._colorbar
    assert arguments['width'] == 600
    assert fig.get_size_inches().tolist() == [6., .8]
    assert bar.extend == 'both' and bar.cmap.N == 5
    assert bar.ax.xaxis.label.get_fontsize() == 8
    assert all(t.get_fontsize() == 7 for t in bar.ax.get_xticklabels())
    assert styled.fill_color.iloc[1] == styled.fill_color.iloc[2]
    assert styled.fill_color.iloc[2] != styled.fill_color.iloc[3]
    for value, marker in zip(values, styled.fill_color):
        expected = (np.array(bar.cmap(bar.norm(value)))[:3]*255).astype(int).tolist()
        assert marker[:3] == expected
    assert styled.metric_value.tolist() == values


def test_storm_steps_match_legend_and_signed_scales_remain_continuous():
    metadata = pd.DataFrame({'station_id':['A','B','C'], 'latitude':[58.,59.,60.],
                             'longitude':[-135.,-136.,-137.]})
    snapshot = pd.DataFrame({'station_id':['A','B','C'], 'absolute_error':[.01,.19,.21]})
    data, _, _ = snapshot_map_data(snapshot, metadata, 'absolute_error', (0.,1.))
    fig = map_colorbar('absolute_error',(0.,1.),'Absolute error','in')
    bar = fig.axes[0]._colorbar
    assert data.fill_color.iloc[0] == data.fill_color.iloc[1]
    assert data.fill_color.iloc[1] != data.fill_color.iloc[2]
    for value, marker in zip(data.absolute_error, data.fill_color):
        assert marker == (np.array(bar.cmap(bar.norm(value)))*255).astype(int).tolist()
    plt.close(fig)
    cmap, norm = color_mapping((-1.,1.), ['blue','white','red'])
    assert norm(0) == .5
    assert cmap(norm(.01)) != cmap(norm(.19))
