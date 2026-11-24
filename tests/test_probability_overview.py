from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from probability import probability_scores, summarize_probability_cases
from probability_overview import build_probability_overview, probability_map_rows
from metrics import compute_station_metrics


def example():
    frame=pd.DataFrame({'station_id':['A','A','A','B','C'],
        'model_value':[0.,0.,2.,2.,0.], 'obs_value':[2.,0.,2.,0.,np.nan]})
    for level in [5,10,25,50,75,90,95]:frame[f'wind_p{level}']=frame.model_value
    return frame


def test_probability_maps_and_overview_use_identical_valid_cases():
    frame=example();frame.index=[9,9,4,4,7]
    metrics=compute_station_metrics(frame,pd.DataFrame(),1,element='wind',probabilistic=True).set_index('station_id')
    assert metrics.loc['A','n_prob']==3
    assert metrics.loc['A','prob_observed_events']==2
    assert metrics.loc['A','zero_probability_events']==1
    assert metrics.loc['A','zero_probability_event_rate_pct']==50
    assert metrics.loc['A','mean_probability_pct']==pytest.approx(100/3)
    assert metrics.loc['A','prob_observed_frequency_pct']==pytest.approx(200/3)
    assert metrics.loc['A','probability_bias_pp']==pytest.approx(-100/3)
    assert np.isnan(metrics.loc['B','zero_probability_event_rate_pct'])
    cases=build_probability_overview(frame,'wind',1,'>=')
    assert cases.station_id.tolist()==['A','A','A','B']
    summary=summarize_probability_cases(cases)
    assert summary['n_prob']==4
    assert summary['zero_probability_event_rate_pct']==50
    assert summary['probability_bias_pp']==0  # Opposing errors cancel; Brier still reports errors.
    assert summary['brier_score']==.5
    assert probability_map_rows(metrics,'probability_bias_pp',3).index.tolist()==['A']
    assert len(probability_map_rows(metrics,'mae',3))==2
    assert len(cases)==4


@pytest.mark.parametrize('operator,event_count,zero_events',[('>=',2,0),('>',1,0),('<=',2,0),('<',1,0)])
def test_operator_equality_preserved(operator,event_count,zero_events):
    frame=pd.DataFrame({'station_id':['A']*3,'model_value':[0,1,2],'obs_value':[0,1,2]})
    for level in [5,10,25,50,75,90,95]:frame[f'wind_p{level}']=frame.model_value
    scores=probability_scores(frame,'wind',1,operator)
    assert scores['prob_observed_events']==event_count
    assert scores['zero_probability_events']==zero_events
    assert scores['brier_score']==0


def test_empty_missing_and_refs_probability_sources():
    frame=example().iloc[:3].copy()
    frame['_forecast_model']='refs';frame['ensemble_eligible']=[True,True,False]
    frame['prob_>_1']=0.  # Unsupported naming must not be used.
    frame['prob_gt_1']=[0.,.000001,1.]
    frame['statistics_config']='{"operator":">","thresholds":[1]}'
    cases=build_probability_overview(frame,'wind',1,'>')
    assert cases.probability_source.eq('archived member probability').all()
    assert len(cases)==2 and cases.forecast_prob.iloc[1]>0
    summary=summarize_probability_cases(cases)
    assert summary['zero_probability_events']==1
    assert summary['n_zero_probability']==1
    empty=probability_scores(frame.iloc[:0],'wind',1,'>')
    assert empty['n_prob']==0 and empty['zero_probability_events']==0
    assert np.isnan(empty['zero_probability_event_rate_pct'])
    # No matched observation never counts as an event/non-event.
    frame.obs_value=np.nan
    assert build_probability_overview(frame,'wind',1,'>').empty


def test_display_scales_and_reliability_precomputed_cases():
    from color_scales import standard_bounds,scale_units
    from config import get_map_metrics
    from plots import plot_threshold_reliability
    import matplotlib.pyplot as plt
    assert standard_bounds('precip6hr','probability_bias_pp')==(-25,25)
    assert standard_bounds('mint','zero_probability_event_rate_pct')==(0,100)
    assert scale_units('wind','probability_bias_pp')=='percentage points'
    assert 'probability_bias_pp' not in get_map_metrics('ndfd','wind')
    cases=build_probability_overview(example(),'wind',1,'>=')
    fig=plot_threshold_reliability(None,1,'nbmqmd','obs','All sites','start','end','wind',probability_data=cases)
    assert sum(bar.get_height() for bar in fig.axes[1].patches)==4
    plt.close(fig)


def test_map_probability_overview_ui_keeps_all_sites_and_downloads(tmp_path):
    from streamlit.testing.v1 import AppTest
    root=Path(__file__).parents[1]/'web_app'
    app=AppTest.from_file(str(root/'pages/1_Map_Explorer.py'),default_timeout=30).run()
    app.selectbox(key='map_ui_model').set_value('nbmqmd').run()
    frame=example();meta=pd.DataFrame({'station_id':['A','B'],'latitude':[58.,59.],'longitude':[-134.,-135.]})
    meta_path=tmp_path/'stations.parquet';meta.to_parquet(meta_path)
    app.secrets.setdefault('local',{})['metadata_path']=str(meta_path)
    app.run()
    metrics=compute_station_metrics(frame,meta,1,element='wind',probabilistic=True)
    app.session_state['station_metrics']=metrics
    app.session_state['map_probability_cases']=build_probability_overview(frame,'wind',1,'>=')
    app.session_state['station_metrics_context']={'model':'nbmqmd','obs':'obs','element':'wind',
        'threshold':1,'threshold_operator':'>=','start_date':'2026-05-01','end_date':'2026-05-31'}
    app.selectbox(key='map_selected_metric').set_value('probability_bias_pp').run()
    assert not app.exception
    assert next(m for m in app.metric if m.label=='Probability cases').value=='4'
    assert len(app.get('imgs'))>=1 or len(app.get('pyplot'))>=1
    assert len(app.dataframe)==0
    app.number_input(key='map_probability_minimum').set_value(3).run()
    app.session_state['selected_station_list']=['B']
    app.run()
    assert not app.exception
    assert next(m for m in app.metric if m.label=='Probability cases').value=='4'
    assert len(app.session_state['map_probability_cases'])==4
    assert any('Map reliability bins' in button.label for button in app.get('download_button'))
    # Edited controls do not relabel the saved plot or rescore the old run.
    app.selectbox(key='map_ui_element').set_value('rh').run()
    assert not app.exception
    assert app.session_state['station_metrics_context']['element']=='wind'
    assert next(m for m in app.metric if m.label=='Probability cases').value=='4'
