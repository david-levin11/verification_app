from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from config import CATEGORY_CONFIG,get_available_category_sets,numeric_category
from category_charts import parse_category_cutoffs,categorical_data


@pytest.mark.parametrize('element,edges',[
    ('maxt',[-40,-20,0,10,20,32,50,70,80]),
    ('mint',[-50,-40,-30,-20,-10,0,10,20,32,50]),
    ('rh',[10,15,20,25,30,40,50,60,70,80,90]),
    ('minrh',[10,15,20,25,30,40,50,60,70,80,90]),
])
def test_default_upper_inclusive_categories_and_tails(element,edges):
    specification=CATEGORY_CONFIG[get_available_category_sets(element)[0]]
    assert specification['bins']==[-np.inf,*edges,np.inf]
    values=[edges[0]-100,*edges,edges[-1]+100]
    pairs=pd.DataFrame(dict(station_id='A',model_value=values,obs_value=values))
    data,counts=categorical_data(pairs,specification)
    assert data.obs_category.tolist()==[0,*range(len(edges)),len(edges)]
    assert counts.values.sum()==len(pairs)
    assert list(counts.index)==list(specification['labels'])
    assert counts.shape==(len(edges)+1,)*2


@pytest.mark.parametrize('text',['','0,0,10','20,0','0,nan','0,inf','foo,10','1,','1;2',','.join(str(i) for i in range(31))])
def test_invalid_custom_categories(text):
    with pytest.raises(ValueError):parse_category_cutoffs(text)


def test_custom_categories_conserve_pairs_and_show_empty_bins():
    cutoffs=parse_category_cutoffs('-10, 0, 32.5, 80')
    specification=numeric_category(cutoffs,'°F')
    frame=pd.DataFrame(dict(station_id=['A']*6,model_value=[-100,-10,0,32.5,81,np.nan],obs_value=[81,-10,0,32.5,-100,0]))
    data,counts=categorical_data(frame,specification)
    assert len(data)==5 and counts.values.sum()==5
    assert counts.loc[0,4]==1 and counts.loc[4,0]==1
    assert counts.loc[3].sum()==0 and counts[3].sum()==0
    assert specification['labels'][0]=='≤-10 °F'
    assert specification['labels'][4]=='>80 °F'
    from plots import plot_forecast_bias_bar_chart,plot_confusion_matrix
    import matplotlib.pyplot as plt
    args=(data,'obs_category','model_category','nbm','obs','All sites','start','end','Day 1',specification['labels'])
    fig=plot_confusion_matrix(*args)
    assert len(fig.axes[0].get_xticklabels())==5
    assert np.asarray(fig.axes[0].collections[0].get_array()).sum()==pytest.approx(100)
    plt.close(fig)
    fig=plot_forecast_bias_bar_chart(*args)
    assert len(fig.axes[0].get_xticklabels())==5
    assert sum(int(text.get_text()[2:]) for text in fig.axes[0].texts)==5
    plt.close(fig)


def test_existing_wind_and_precip_categories_unchanged():
    assert CATEGORY_CONFIG['marine']['bins']==[-.1,25,33,48,63,np.inf]
    assert CATEGORY_CONFIG['marine']['labels'][1]=='SCA'
    assert CATEGORY_CONFIG['beaufort']['labels'][3]=='Gentle Breeze'
    assert CATEGORY_CONFIG['precip']['bins']==[-.001,.01,.1,.25,.5,1,2,np.inf]


def test_map_overview_tabs_custom_defaults_and_saved_context(tmp_path):
    from streamlit.testing.v1 import AppTest
    from metrics import compute_station_metrics
    root=Path(__file__).parents[1]/'web_app'
    meta=pd.DataFrame(dict(station_id=['A','B'],latitude=[58.,np.nan],longitude=[-134.,np.nan]))
    path=tmp_path/'stations.parquet';meta.to_parquet(path)
    app=AppTest.from_file(str(root/'pages/1_Map_Explorer.py'),default_timeout=30).run()
    app.secrets.setdefault('local',{})['metadata_path']=str(path)
    app.run()
    app.selectbox(key='map_ui_element').set_value('maxt').run()
    pairs=pd.DataFrame(dict(station_id=['A','B','B'],model_value=[-45,32,90],obs_value=[-40,20,80]))
    app.session_state['station_metrics']=compute_station_metrics(pairs,meta,32)
    app.session_state['map_chart_cases']=pairs
    app.session_state['station_metrics_context']=dict(element='maxt',model='nbm',obs='obs',percentile=None,
        start_date='2026-05-01',end_date='2026-05-31',forecast_projection='Day 1')
    app.run()
    assert not app.exception
    assert 'All-Sites Overview' in [tab.label for tab in app.tabs]
    assert len(app.dataframe)==0
    assert any('3 forecast/observation pairs across 2 stations' in c.value for c in app.caption)
    mode='map_chart_category_mode_maxt_maxt';edges='map_chart_category_edges_maxt_maxt'
    app.selectbox(key=mode).set_value('Custom').run()
    app.text_input(key=edges).set_value('0, 32, 70').run()
    assert not app.exception and not app.error
    assert any('>70 °F' in c.value for c in app.caption)
    app.text_input(key=edges).set_value('32, 0').run()
    assert not app.exception
    assert any('Showing the default categories' in e.value for e in app.error)
    assert any('>80 °F' in c.value for c in app.caption)
    app.selectbox(key=mode).set_value('Default').run()
    app.session_state['selected_station_list']=['A']
    app.selectbox(key='map_ui_element').set_value('rh').run()
    assert not app.exception
    assert any('3 forecast/observation pairs across 2 stations' in c.value for c in app.caption)
    assert app.session_state['station_metrics_context']['element']=='maxt'
    assert any('Chart category definitions' in b.label for b in app.get('download_button'))


def test_aggregate_custom_categories_are_independent_of_map_controls():
    from streamlit.testing.v1 import AppTest
    from metrics import compute_summary_metrics
    root=Path(__file__).parents[1]/'web_app'
    pairs=pd.DataFrame(dict(station_id=['A','A'],model_value=[5.,45.],obs_value=[0.,40.]))
    app=AppTest.from_file(str(root/'pages/2_Aggregate_Verification.py'),default_timeout=30).run()
    app.session_state['aggregate_merged']=pairs
    app.session_state['aggregate_summary']=compute_summary_metrics(pairs,32)
    app.session_state['aggregate_context']=dict(model='nbm',element='mint',obs='obs',percentile=None,
        category_set='mint',group_name='Selected stations',start_date='2026-05-01',end_date='2026-05-31',
        forecast_projection='Day 1',threshold=32,threshold_operator='<=')
    app.run()
    assert not app.exception
    assert any('≤-50 °F' in c.value for c in app.caption)
    mode='aggregate_chart_category_mode_mint_mint';edges='aggregate_chart_category_edges_mint_mint'
    app.selectbox(key=mode).set_value('Custom').run()
    app.text_input(key=edges).set_value('0, 32').run()
    assert not app.exception
    assert any('>32 °F' in c.value for c in app.caption)
    assert app.session_state['aggregate_summary']['mae']==5
    assert len(app.session_state['aggregate_merged'])==2
    assert len(app.dataframe)==0
    assert 'map_chart_category_mode_mint_mint' not in app.session_state
