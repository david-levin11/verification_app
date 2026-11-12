"""Native MinRH periods, coverage QC, deterministic scoring and all four pages."""
from datetime import date
from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from minrh import prepare_minrh
from pairing import build_verification_pairs
from comparison import comparison_cases,comparison_scores
from config import get_available_elements,is_probabilistic,get_element_config
from storm_initialization import initialization_hours


def fixture(root):
    ends=pd.to_datetime(['2026-05-31 06:00','2026-05-31 06:00','2026-06-01 06:00','2026-06-01 06:00'])
    init=pd.Timestamp('2026-05-30 12:00')
    m=pd.DataFrame({'station_id':['A','B','A','B'],'init_time':init,'valid_time':ends,
        'forecast_hour':(ends-init).total_seconds()/3600,'minrh':[25.,35.,5.,55.]})
    o=pd.DataFrame({'stid':m.station_id,'valid_time':ends,'window_end':ends,
        'window_start':ends-pd.Timedelta(hours=12),'minrh':[20.,40.,0.,60.],
        'coverage_ok':True,'n_obs':12,'max_gap_minutes':60.,'rh_units':'%'})
    n=m.assign(window_start=ends-pd.Timedelta(hours=12),window_end=ends,
               window_hours=12.,window_duration_mismatch=False)
    for model,df in [('nbm',m),('ndfd',n),('obs',o)]:
        folder=root/model/'minrh';folder.mkdir(parents=True)
        months=df.valid_time.dt.strftime('%Y_%m') if model=='obs' else df.init_time.dt.strftime('%Y_%m')
        for month,part in df.groupby(months):part.to_parquet(folder/f'{month}_archive.parquet',index=False)
    meta=root/'stations.parquet'
    pd.DataFrame({'station_id':['A','B'],'latitude':[58.,60.],'longitude':[-135.,-150.]}).to_parquet(meta)
    return m,n,o,meta


def test_configuration_and_source_cycles():
    assert 'minrh' in get_available_elements('nbm') and 'minrh' in get_available_elements('ndfd')
    for model in ['nbm','ndfd']:
        assert not is_probabilistic(model,'minrh')
    for model in ['nbmqmd','refs','rrfs','hrrr']:
        assert 'minrh' not in get_available_elements(model)
    assert get_element_config('minrh')['threshold_operator']=='<='
    assert initialization_hours('nbm','minrh')==[0,12]


def test_coverage_zero_clipped_period_and_shared_cases(tmp_path):
    m,n,o,_=fixture(tmp_path)
    pairs=build_verification_pairs(m,o,'nbm','obs','minrh',obs_time_tolerance='1h')
    assert len(pairs)==4 and 0 in pairs.obs_value.values
    assert pairs.obs_window_start.eq(pairs.model_window_start).all()
    bad=n.iloc[[0]].copy();bad['window_start']=bad.valid_time-pd.Timedelta(hours=6)
    bad['window_duration_mismatch']=True
    assert prepare_minrh(bad,'ndfd')[0].empty
    assert build_verification_pairs(bad,o,'ndfd','obs','minrh',obs_time_tolerance='12h').empty
    sparse=o.copy();sparse.loc[0,'coverage_ok']=False
    assert len(build_verification_pairs(m,sparse,'nbm','obs','minrh'))==3
    cases,diag=comparison_cases(n,m,o,'ndfd','nbm','minrh',reference_tolerance='0h',lead_max=174)
    assert len(cases)==4 and diag['matched_cases']==4
    _,a,b=comparison_scores(cases,'minrh',30,'<=')
    assert a['pod']==b['pod']==1 and a['mae']==b['mae']==5


@pytest.mark.parametrize('change',[{'minrh':101},{'minrh':-1},{'minrh':float('inf')},
    {'minrh':False},{'coverage_ok':False},{'coverage_ok':None},{'rh_units':'fraction'},
    {'window_start':pd.Timestamp('2026-05-30 17:00')}])
def test_invalid_observations_are_not_used(tmp_path,change):
    _,_,o,_=fixture(tmp_path)
    row=o.iloc[[0]].copy()
    for key,value in change.items():row[key]=value
    clean,notes=prepare_minrh(row)
    assert clean.empty and notes


def test_loader_month_boundary_and_diagnostics(tmp_path):
    from comparison_loader import load_comparison_data
    from data_loader import fetch_data
    m,n,o,_=fixture(tmp_path)
    # A clipped NDFD row cannot replace a full 12-hour case, even at one endpoint.
    n.loc[0,'window_duration_mismatch']=True
    n.to_parquet(tmp_path/'ndfd/minrh/2026_05_archive.parquet',index=False)
    a,b,obs,notes=load_comparison_data(tmp_path,'ndfd','nbm','obs','minrh',date(2026,6,1),date(2026,6,1),['A','B'])
    assert len(a)==len(b)==len(obs)==2
    a,b,obs,notes=load_comparison_data(tmp_path,'ndfd','nbm','obs','minrh',date(2026,5,31),date(2026,6,1),['A','B'])
    assert len(a)==3 and len(b)==len(obs)==4 and any('excluded 1' in note for note in notes)


def test_all_pages_score_minrh_without_percentiles(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import storm_visuals
    _,_,_,meta=fixture(tmp_path)
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kwargs:None)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20)
    app.secrets['local']={'archive_root':str(tmp_path),'metadata_path':str(meta)}
    app.run()
    for page,button,result in [('map','Build Station Metric Map','station_metrics'),('aggregate','Run Aggregate Verification','aggregate_summary')]:
        app.switch_page('pages/1_Map_Explorer.py' if page=='map' else 'pages/2_Aggregate_Verification.py').run()
        if page=='aggregate':app.text_input(key='aggregate_station_ids_input').set_value('A,B')
        app.selectbox(key=f'{page}_ui_model').set_value('nbm').run()
        app.selectbox(key=f'{page}_ui_element').set_value('minrh').run()
        app.date_input(key=f'{page}_ui_start_date').set_value(date(2026,5,31))
        app.date_input(key=f'{page}_ui_end_date').set_value(date(2026,6,1))
        app.checkbox(key=f'{page}_ui_use_all_forecast_hours').set_value(True).run()
        assert not any(s.label=='Verification Percentile' for s in app.selectbox)
        next(b for b in app.button if b.label==button).click().run(timeout=30)
        assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
        score=app.session_state[result]
        assert (score.n.sum() if page=='map' else score['n'])==4
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.selectbox(key='storm_Model').set_value('nbm').run()
    app.selectbox(key='storm_Element').set_value('minrh').run()
    app.date_input(key='storm_init_date').set_value(date(2026,5,30))
    app.selectbox(key='storm_init_hour').set_value(12)
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,5,31))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,6,1))
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
    assert app.session_state['storm_result']['cases'].obs_value.notna().sum()==4
    app.switch_page('pages/4_Model_Comparison.py').run()
    app.selectbox(key='compare_model_a').set_value('ndfd').run()
    app.selectbox(key='compare_model_b').set_value('nbm').run()
    app.selectbox(key='compare_element').set_value('minrh').run()
    app.text_input(key='compare_stations').set_value('A,B')
    app.date_input(key='compare_start').set_value(date(2026,5,31))
    app.date_input(key='compare_end').set_value(date(2026,6,1))
    next(b for b in app.button if b.label=='Run Model Comparison').click().run(timeout=30)
    assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
    assert len(app.session_state['comparison_result']['cases'])==4


def test_reference_offset_and_required_bounds(tmp_path):
    m,n,o,_=fixture(tmp_path)
    m['init_time']-=pd.Timedelta(hours=6)
    m['forecast_hour']+=6
    cases,diag=comparison_cases(n,m,o,'ndfd','nbm','minrh',offset_hours=-6,
                               reference_tolerance='1h',lead_max=174)
    assert len(cases)==4 and cases.actual_offset_hours.eq(-6).all()
    assert cases.obs_window_end.eq(cases.a_valid_time).all()
    with pytest.raises(ValueError,match='explicit window'):
        prepare_minrh(n.drop(columns=['window_start','window_end']),'ndfd')
    with pytest.raises(ValueError,match='coverage_ok'):
        prepare_minrh(o.drop(columns='coverage_ok'))


def test_window_metadata_and_plots(tmp_path):
    from storm_analysis import build_storm_cases
    from accumulation_storm import plot_accumulation_periods
    from storm_visuals import map_description
    import matplotlib.pyplot as plt
    m,n,o,_=fixture(tmp_path)
    n['window_hours']=6
    assert prepare_minrh(n,'ndfd')[0].empty
    cases=build_storm_cases(m,o,'nbm','obs','minrh',m.init_time.iloc[0])
    assert cases.coverage_ok.all() and cases.n_obs.eq(12).all()
    fig=plot_accumulation_periods(cases,'A','nbm','minrh',None,30,'<=')
    assert fig.axes[0].get_ylim()==(0.,100.)
    assert 'Minimum-RH' in fig.axes[0].get_xlabel()
    assert any(line.get_label()=='Matched observed minimum' for line in fig.axes[0].lines)
    plt.close(fig)
    text=map_description('obs_value','Observation',get_element_config('minrh'),None,30,'<=')
    assert 'minimum RH' in text and 'total' not in text
