"""RRFS/REFS adapters, variable separation, membership and probability semantics."""
from datetime import date
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
import pytest
import duckdb
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from config import get_available_elements,is_probabilistic,get_percentile_columns
from data_loader import fetch_data
from comparison_loader import load_comparison_data
from comparison import comparison_cases,comparison_scores
from pairing import build_verification_pairs
from probability import forecast_probability_details,probability_scores
from forecast_archive import register_forecast_archive
from storm_analysis import build_storm_cases


def fixture(root,element='wind',custom=False):
    init=pd.Timestamp('2026-09-30 18:00')
    leads=[6,42,48,54,60]
    expected=[14,14,13,12,6]
    scalar={'wind':'wind_speed_kt','gust':'wind_gust_kt','rh':'rh','precip6hr':'precip_6h'}[element]
    variable=scalar
    derived=root/'custom_derived' if custom else root/'derived/refs'
    model=root/'model'
    rows=[];det=[];obs=[]
    for station in ['A','B']:
        for lead,count in zip(leads,expected):
            valid=init+pd.Timedelta(hours=lead)
            row=dict(station_id=station,ensemble_init_time=init,ensemble_forecast_hour=lead,
                valid_time=valid,value_column=variable,n_expected=count,n_available=count,complete=True,
                mean=20.,spread=5.,probability_operator='<' if element=='rh' else '>',require_complete=True,
                statistics_config=json.dumps(dict(operator='<' if element=='rh' else '>',thresholds=[25.])),
                prob_lt_25=.125 if element=='rh' else np.nan,prob_gt_25=.375 if element!='rh' else np.nan)
            row.update({f'p{p}':float(p)/2 for p in [5,10,25,50,75,90,95]})
            # One genuine missing-member case; +60 with 6/6 remains valid.
            if station=='B' and lead==42:
                row.update(n_available=count-1,complete=False)
            rows.append(row)
            if element in ['wind','gust']:
                other=row.copy();other['value_column']='wind_gust_kt' if element=='wind' else 'wind_speed_kt'
                other.update({f'p{p}':999. for p in [5,10,25,50,75,90,95]})
                rows.append(other)
            det.append(dict(station_id=station,init_time=init,valid_time=valid,forecast_hour=lead,**{scalar:25.},wind_dir_deg=180.))
            ob=dict(stid=station,valid_time=valid-pd.Timedelta(minutes=7))
            if element=='precip6hr':ob.update(end_time=ob['valid_time'],start_time=ob['valid_time']-pd.Timedelta(hours=6),precip_total=25.)
            else:ob[{'wind':'obs_wind_speed_kts','gust':'obs_wind_gust_kts','rh':'rh'}[element]]=25.
            obs.append(ob)
    source='wind' if element=='gust' else element
    for folder,frame,times in [(derived/source,pd.DataFrame(rows),'ensemble_init_time'),
                                (model/'rrfs'/source,pd.DataFrame(det),'init_time'),
                                (model/'obs'/source,pd.DataFrame(obs),'valid_time')]:
        folder.mkdir(parents=True,exist_ok=True)
        for month,part in frame.groupby(frame[times].dt.strftime('%Y_%m')):
            part.to_parquet(folder/f'{month}_archive.parquet',index=False)
    # Gust observations are intentionally in wind/ and use the normal fallback.
    from test_storm_analysis import metadata
    meta=root/'metadata.parquet';metadata().to_parquet(meta,index=False)
    return model,derived,init,meta


@pytest.mark.parametrize('element',['wind','gust','rh','precip6hr'])
@pytest.mark.parametrize('custom',[False,True])
def test_both_loaders_all_leads_shared_scores_and_actual_member_counts(tmp_path,element,custom):
    root,derived,init,_=fixture(tmp_path,element,custom)
    kwargs={'refs_root':derived} if custom else {}
    a,b,o,warnings=load_comparison_data(root,'refs','rrfs','obs',element,date(2026,10,1),date(2026,10,3),['A','B'],**kwargs)
    assert len(a)==10 and set(a.value_column)=={{'wind':'wind_speed_kt','gust':'wind_gust_kt','rh':'rh','precip6hr':'precip_6h'}[element]}
    assert a.ensemble_eligible.sum()==9
    assert a.loc[a.forecast_hour.eq(60),'n_available'].eq(6).all()
    assert a.loc[a.forecast_hour.eq(60),'complete'].all()
    assert get_percentile_columns(element)['50'] in a
    assert a.loc[~a.ensemble_eligible,get_percentile_columns(element)['50']].isna().all()
    cases,d=comparison_cases(a,b,o,'refs','rrfs',element,'50',None)
    assert len(cases)==9 and cases.a_forecast_hour.eq(60).sum()==2
    table,sa,sb=comparison_scores(cases,element,25,'<' if element=='rh' else '>',True,False)
    assert sa['n_prob']==9 and sa['mae']==0 and sb['mae']==0
    av=cases[[c for c in cases if c.startswith('a_')]].rename(columns=lambda c:c[2:])
    details=forecast_probability_details(av,element,25,'<' if element=='rh' else '>')
    np.testing.assert_allclose(details.forecast_prob,.125 if element=='rh' else .375)
    assert details.probability_source.eq('archived member probability').all()
    loaded,observations,message=fetch_data('Storm Specific Zoom','refs','obs',date(2026,10,1),date(2026,10,3),
        ['A','B'],[],init,{},'50',element=element,archive_root=root,**kwargs)
    storm=build_storm_cases(loaded,observations,'refs','obs',element,init,'50',threshold=25,operator='<' if element=='rh' else '>')
    assert len(storm)==9 and storm.forecast_hour.eq(60).sum()==2
    assert storm.probability_source.eq('archived member probability').all()
    assert '1 of 10' in message
    assert all(e in get_available_elements('refs') for e in ['wind','gust','rh','precip6hr'])
    assert is_probabilistic('refs',element) and not is_probabilistic('rrfs',element)


def test_probability_operator_recipe_nan_and_incomplete_rules(tmp_path):
    root,_,_,_=fixture(tmp_path)
    a,_,o,_=load_comparison_data(root,'refs','rrfs','obs','wind',date(2026,10,1),date(2026,10,3),['A','B'])
    assert forecast_probability_details(a,'wind',25,'>=').probability_source.eq('quantile approximation').sum()==9
    details=forecast_probability_details(a,'wind',25,'>')
    assert details.forecast_prob.notna().sum()==9
    a['prob_gt_25']=np.nan
    assert forecast_probability_details(a,'wind',25,'>').forecast_prob.isna().all()
    assert forecast_probability_details(a,'wind',26,'>').forecast_prob.notna().sum()==9
    a['prob_gt_25']=1.2
    assert forecast_probability_details(a,'wind',25,'>').forecast_prob.isna().all()
    # A column contributed by a different variable's recipe does not define this event.
    a['statistics_config']=json.dumps(dict(operator='>',thresholds=[34]))
    assert forecast_probability_details(a,'wind',25,'>').probability_source.eq('quantile approximation').sum()==9


def test_rrfs_legacy_precip_uses_exact_endpoints_before_date_or_lead_filters(tmp_path):
    init=pd.Timestamp('2026-09-30 18:00')
    hours=[3,6,9,12,18]
    frame=pd.DataFrame(dict(station_id='A',init_time=init,forecast_hour=hours,
        valid_time=[init+pd.Timedelta(hours=h) for h in hours],precip_accum=[.1,.3,.6,1.,1.8]))
    path=tmp_path/'totals.parquet';frame.to_parquet(path,index=False)
    with duckdb.connect() as con:
        register_forecast_archive(con,[str(path)],'rrfs','precip6hr')
        result=con.sql('SELECT * FROM forecast_archive ORDER BY forecast_hour').df()
    np.testing.assert_allclose(result.verification_precip_6h,[np.nan,.3,.5,.7,.8],equal_nan=True)
    frame=frame[~frame.forecast_hour.eq(6)]
    frame.to_parquet(path,index=False)
    with duckdb.connect() as con:
        register_forecast_archive(con,[str(path)],'rrfs','precip6hr')
        assert con.execute('SELECT verification_precip_6h FROM forecast_archive WHERE forecast_hour=12').fetchone()[0] is None
    # An existing interval column is authoritative, including missing values.
    frame['precip_6h']=np.nan;frame.to_parquet(path,index=False)
    with duckdb.connect() as con:
        register_forecast_archive(con,[str(path)],'rrfs','precip6hr')
        assert con.execute('SELECT count(verification_precip_6h) FROM forecast_archive').fetchone()[0]==0


def test_mixed_old_and_new_precip_files_keep_schema_specific_missing_values(tmp_path):
    init=pd.Timestamp('2026-09-30 18:00')
    old=pd.DataFrame(dict(station_id='A',init_time=init,valid_time=[init+pd.Timedelta(hours=h) for h in [6,12]],
        forecast_hour=[6,12],precip_accum=[1.,3.]))
    new=old.copy();new['init_time']+=pd.Timedelta(days=1);new['valid_time']+=pd.Timedelta(days=1)
    new['precip_6h']=[.5,np.nan]
    paths=[tmp_path/'old.parquet',tmp_path/'new.parquet']
    for path,frame in zip(paths,[old,new]):frame.to_parquet(path,index=False)
    with duckdb.connect() as con:
        register_forecast_archive(con,list(map(str,paths)),'rrfs','precip6hr')
        result=con.sql('SELECT * FROM forecast_archive ORDER BY init_time,forecast_hour').df()
    np.testing.assert_allclose(result.verification_precip_6h,[1.,2.,.5,np.nan],equal_nan=True)


@pytest.mark.parametrize('element',['wind','gust','rh','precip6hr'])
@pytest.mark.parametrize('model',['rrfs','refs'])
def test_models_run_all_four_pages(tmp_path,monkeypatch,element,model):
    from streamlit.testing.v1 import AppTest
    import storm_visuals
    root,derived,init,meta=fixture(tmp_path,element,custom=True)
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kwargs:None)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20).run()
    for page,button,result in [('map','Build Station Metric Map','station_metrics'),
                              ('aggregate','Run Aggregate Verification','aggregate_summary')]:
        app.switch_page('pages/1_Map_Explorer.py' if page=='map' else 'pages/2_Aggregate_Verification.py').run()
        if page=='map':app.text_input(key='map_metadata_path').set_value(str(meta)).run()
        else:app.text_input(key='aggregate_station_ids_input').set_value('A,B')
        app.text_input(key=f'{page}_ui_archive_root').set_value(str(root))
        app.selectbox(key=f'{page}_ui_model').set_value(model).run()
        app.selectbox(key=f'{page}_ui_element').set_value(element).run()
        if model=='refs':
            app.text_input(key=f'{page}_refs_root').set_value(str(derived))
            app.selectbox(key=f'{page}_ui_percentile').set_value('50')
        app.date_input(key=f'{page}_ui_start_date').set_value(date(2026,10,1))
        app.date_input(key=f'{page}_ui_end_date').set_value(date(2026,10,3))
        app.checkbox(key=f'{page}_ui_use_all_forecast_hours').set_value(True).run()
        next(b for b in app.button if b.label==button).click().run(timeout=30)
        assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
        score=app.session_state[result]
        assert (score.n.sum() if page=='map' else score['n'])==(9 if model=='refs' else 10)
    app.switch_page('pages/3_Storm_Zoom.py').run()
    app.text_input(key='storm_Local Archive Root').set_value(str(root))
    app.text_input(key='storm_metadata').set_value(str(meta))
    app.selectbox(key='storm_Model').set_value(model).run()
    app.selectbox(key='storm_Element').set_value(element).run()
    app.checkbox(key='storm_compare_enabled').set_value(True).run()
    app.selectbox(key='storm_model_b').set_value('refs' if model=='rrfs' else 'rrfs').run()
    app.text_input(key='storm_refs_root').set_value(str(derived))
    if model=='refs':app.selectbox(key=f'storm_percentile_{element}').set_value('50')
    app.text_input(key='storm_Model Init Time (YYYY-MM-DD HH:MM:SS)').set_value(str(init))
    app.date_input(key='storm_Plot Start Date').set_value(date(2026,10,1))
    app.date_input(key='storm_Plot End Date').set_value(date(2026,10,3))
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run(timeout=30)
    assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
    assert len(app.session_state['storm_result']['shared'])==9
    assert app.session_state['storm_result']['shared'].a_forecast_hour.eq(60).sum()==2
    app.switch_page('pages/4_Model_Comparison.py').run()
    app.text_input(key='compare_archive_root').set_value(str(root))
    app.text_input(key='compare_stations').set_value('A,B')
    app.selectbox(key='compare_model_a').set_value('refs').run()
    app.selectbox(key='compare_model_b').set_value('rrfs').run()
    app.selectbox(key='compare_element').set_value(element).run()
    app.text_input(key='compare_refs_root').set_value(str(derived))
    app.selectbox(key=f'compare_pct_a_{element}').set_value('50')
    app.date_input(key='compare_start').set_value(date(2026,10,1))
    app.date_input(key='compare_end').set_value(date(2026,10,3))
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error,[e.value for e in app.exception]+[e.value for e in app.error]
    result=app.session_state['comparison_result']
    assert len(result['cases'])==9 and result['summary_a']['n_prob']==9
