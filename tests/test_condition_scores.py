"""Threshold event denominators remain explicit in observed-category plots."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parents[1]/'web_app'))
from comparison import grouped_scores
from comparison_plots import plot_group_scores


def test_many_low_wind_cases_have_no_events_for_high_threshold_pod():
    # Lower categories are well sampled, but those observations are not >=25 kt.
    cases = pd.DataFrame(dict(station_id=['A']*102,obs_value=[5.]*100+[26.,27.],
        a_model_value=[6.]*100+[26.,20.], b_model_value=[4.]*100+[20.,20.],
        condition=['Light Breeze']*100+['Strong Breeze']*2))
    scores = grouped_scores(cases,'condition','wind',25)
    pod = scores[scores.metric.eq('pod')].set_index('condition')
    assert pod.loc['Light Breeze','n'] == 100
    assert pod.loc['Light Breeze','observed_events'] == 0
    assert np.isnan(pod.loc['Light Breeze','a'])
    assert pod.loc['Light Breeze','better'] == 'Unavailable'
    assert pod.loc['Strong Breeze','observed_events'] == 2
    assert pod.loc['Strong Breeze','a'] == .5
    assert pod.loc['Strong Breeze','b'] == 0
    figure = plot_group_scores(scores,'condition','pod','A','B','Observed category')
    ax = figure.axes[0]
    assert [text.get_text() for text in ax.get_xticklabels()] == ['Light Breeze','Strong Breeze']
    assert any(text.get_text() == 'N/A' for text in ax.texts)
    plt.close(figure)


def test_one_models_undefined_far_does_not_hide_the_other_model():
    scores = pd.DataFrame(dict(metric=['far'],condition=['Light Breeze'],
        a=[np.nan],b=[1.]))
    figure = plot_group_scores(scores,'condition','far','A','B','Observed category')
    ax = figure.axes[0]
    assert ax.lines[1].get_ydata().tolist() == [1.]
    assert [text.get_text() for text in ax.get_xticklabels()] == ['Light Breeze']
    plt.close(figure)
