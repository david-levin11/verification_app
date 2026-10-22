"""Storm map color bars and question-based explanations."""
from pathlib import Path
import sys
import numpy as np
import pytest
import matplotlib.pyplot as plt

sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from config import get_element_config
from storm_visuals import map_colorbar,map_colormap,map_description


@pytest.mark.parametrize('metric,limits,unit',[('error',(-10,10),'kt'),
    ('median_error',(-5,5),'percentage points'),('observed_percentile',(0,100),'percentile'),
    ('forecast_probability',(0,1),'probability'),('width_25_75',(0,20),'kt'),
    ('angular_error',(0,180),'degrees'),('model_value',(0,40),'kt')])
def test_colorbar_uses_marker_colormap_and_actual_limits(metric,limits,unit):
    figure=map_colorbar(metric,limits,'Test display',unit)
    bar=figure.axes[0]._colorbar
    assert (bar.norm.vmin,bar.norm.vmax)==limits
    assert np.allclose(bar.cmap(.25),map_colormap(metric)(.25))
    if metric=='forecast_probability':
        assert bar.formatter(.5)=='50%'
        assert figure.axes[0].get_xlabel()=='Test display (%)'
    else:assert unit in figure.axes[0].get_xlabel()
    plt.close(figure)


@pytest.mark.parametrize('metric',['model_value','obs_value','error','absolute_error',
    'median_error','observed_percentile','forecast_probability','angular_error','width_25_75'])
def test_each_display_explains_its_question(metric):
    text=map_description(metric,'Display',get_element_config('rh'),'75',30,'<=')
    assert text.startswith('Display answers the question:') and '?' in text
    if metric=='forecast_probability':assert '<= 30 %' in text
    if metric=='width_25_75':assert 'central 50%' in text
    if metric=='median_error':assert 'p50' in text and 'p75' not in text
    if metric=='error':assert 'p75' in text and 'Positive values' in text
