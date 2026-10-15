"""Circular errors, common case filters, and synthetic archive page flows."""
import sys
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'web_app'))
from comparison import comparison_cases, comparison_scores
from wind_verification import (normalize_direction, absolute_angular_error,
    filter_observed_speed, filter_observed_sector, direction_cases,
    direction_scores, direction_exceedance, grouped_direction_scores)


def test_circular_errors_north_wrap_and_sentinels():
    forecast = pd.Series([350, 10, 360, 0, 180, -999, 361, np.nan, np.inf, 'bad'])
    observed = pd.Series([10, 350, 0, 360, 0, 0, 0, 0, 0, 0])
    error = absolute_angular_error(forecast, observed)
    assert error.iloc[:5].tolist() == [20, 20, 0, 0, 180]
    assert error.iloc[5:].isna().all()
    assert normalize_direction(pd.Series([0, 360])).tolist() == [0, 0]


def raw_wind_cases():
    return pd.DataFrame(dict(station_id=['A']*7,
        target_time=pd.date_range('2026-06-01', periods=7), lead_day=[1,1,1,2,2,2,2],
        obs_value=[5,4.9,10,10,10,0,10], a_model_value=[10,10,10,10,0,10,10],
        b_model_value=[10]*7, a_forecast_direction=[350,10,np.nan,10,10,0,180],
        b_forecast_direction=[100,10,10,361,10,0,0], observed_direction=[10,10,10,10,10,0,0]))


def test_direction_uses_common_valid_subset_and_counts_each_exclusion():
    original = raw_wind_cases()
    cases, diag = direction_cases(original, 5)
    assert cases.index.tolist() == [0, 6]
    assert cases.a_angular_error.tolist() == [20,180]
    assert cases.b_angular_error.tolist() == [90,0]
    assert diag == dict(input_cases=7, missing_fields=[], invalid_directions=2,
        below_observed_minimum_or_calm=2, nonpositive_forecast_speed=1, direction_cases=2)
    assert 'a_angular_error' not in original
    # Calm forecasts are still retained in speed verification.
    assert 4 in filter_observed_speed(original, 5).index
    zero, _ = direction_cases(original, 0)
    assert 5 not in zero.index  # zero-speed observation has no defined direction
    missing, missing_diag = direction_cases(original.drop(columns='b_forecast_direction'))
    assert missing.empty and missing_diag['missing_fields'] == ['b_forecast_direction']


def test_direction_summary_exceedance_strict_threshold_and_groups():
    cases = pd.DataFrame(dict(a_angular_error=[0.,45.,180.], b_angular_error=[20.,90.,180.],
                              station_id=['A','A','B'], lead_day=[1,1,2]))
    scores = direction_scores(cases, 45).set_index('metric')
    assert scores.loc['angular_mae','a'] == 75
    assert scores.loc['angular_median','a'] == 45
    assert scores.loc['exceedance_percent','a'] == pytest.approx(100/3)
    assert scores.loc['exceedance_percent','b'] == pytest.approx(200/3)
    assert scores.better.eq('A').all()
    curve = direction_exceedance(cases, [0,45,180])
    assert curve.a.tolist() == pytest.approx([200/3,100/3,0])
    assert curve.b.tolist() == pytest.approx([100,200/3,0])
    assert (np.diff(direction_exceedance(cases).a) <= 0).all()
    table = grouped_direction_scores(cases, 'station_id', 45)
    assert table[table.station_id.eq('A')].n.eq(2).all()
    assert table[table.station_id.eq('B')].better.eq('Tie').all()
    assert direction_scores(cases.iloc[:0]).a.isna().all()
    assert direction_exceedance(cases.iloc[:0]).a.isna().all()
    with pytest.raises(ValueError): direction_scores(cases, 181)
    with pytest.raises(ValueError): direction_cases(raw_wind_cases(), -1)
    with pytest.raises(ValueError): filter_observed_speed(raw_wind_cases(), np.nan)


def test_speed_filter_equality_and_wrapping_observed_sector():
    cases = pd.DataFrame(dict(obs_value=[4.9,5,10,np.nan], observed_direction=[360,0,45,-999]))
    assert filter_observed_speed(cases, 5).index.tolist() == [1,2]
    assert len(filter_observed_speed(cases)) == 4
    assert filter_observed_sector(cases, 315,45).index.tolist() == [0,1,2]
    assert filter_observed_sector(cases,0,360).index.tolist() == [0,1,2]
    assert filter_observed_sector(cases,90,270).empty


def archive_fixture(tmp_path, obs_direction_column='obs_wind_dir_deg'):
    valid = pd.to_datetime(['2026-06-02 00:00','2026-06-02 06:00'])
    a = pd.DataFrame(dict(station_id=['A']*2, valid_time=valid, forecast_hour=[24]*2,
                          wind_speed_kt=[20.,20.], wind_dir_deg=[350.,10.]))
    b = pd.DataFrame(dict(station_id=['A']*2, valid_time=valid, forecast_hour=[30]*2,
        init_time=valid-pd.Timedelta(hours=30), wind_speed_kt=[25.,25.], wind_dir_deg=[100.,170.]))
    obs = pd.DataFrame(dict(stid=['A']*2, valid_time=valid-pd.Timedelta(minutes=7),
                           obs_wind_speed_kts=[2.,10.]))
    obs[obs_direction_column] = [10.,350.]
    for model, frame in [('ndfd',a), ('nbm',b), ('obs',obs)]:
        folder = tmp_path/model/'wind'; folder.mkdir(parents=True)
        if model == 'nbm':
            frame.loc[[0]].to_parquet(folder/'2026_05_archive.parquet',index=False)
            frame.loc[[1]].to_parquet(folder/'2026_06_archive.parquet',index=False)
        else:
            frame.to_parquet(folder/'2026_06_archive.parquet',index=False)
    qmd = b.drop(columns=['wind_speed_kt','wind_dir_deg']).copy()
    for pct in [5,10,25,50,75,90,95]: qmd[f'wind_p{pct}'] = [25.,25.]
    for model in ['nbmqmd','nbmqmd_exp']:
        folder = tmp_path/model/'wind'; folder.mkdir(parents=True)
        qmd.loc[[0]].to_parquet(folder/'2026_05_archive.parquet',index=False)
        qmd.loc[[1]].to_parquet(folder/'2026_06_archive.parquet',index=False)
    return a,b,obs,qmd


@pytest.mark.parametrize('obs_direction_column', ['obs_wind_dir_deg','wind_dir_deg'])
def test_direction_pairing_keeps_same_53_report_and_reference_offset(tmp_path, obs_direction_column):
    a,b,obs,_ = archive_fixture(tmp_path, obs_direction_column)
    # A nearby second report has a different direction. Its direction must not leak in.
    extra = obs.iloc[[1]].copy(); extra.valid_time += pd.Timedelta(minutes=20)
    extra[obs_direction_column] = 200
    obs = pd.concat([obs,extra],ignore_index=True)
    paired, _ = comparison_cases(a,b,obs,'ndfd','nbm','wind',offset_hours=-6,obs_time_tolerance='15min')
    assert paired.actual_offset_hours.eq(-6).all()
    assert paired.obs_time_offset_minutes.eq(-7).all()
    assert paired.observed_direction.tolist() == [10,350]
    directions, _ = direction_cases(paired)
    assert directions.a_angular_error.tolist() == [20]
    assert directions.b_angular_error.tolist() == [180]
    assert directions.obs_value.tolist() == [10]
    no_ob_dir = obs.drop(columns=obs_direction_column)
    without, _ = comparison_cases(a,b,no_ob_dir,'ndfd','nbm','wind',offset_hours=-6)
    _, diag = direction_cases(without)
    assert diag['missing_fields'] == ['observed_direction']


def test_minimum_speed_filters_both_probability_models_on_common_cases(tmp_path):
    _,_,obs,qmd = archive_fixture(tmp_path)
    paired,_ = comparison_cases(qmd,qmd,obs,'nbmqmd','nbmqmd_exp','wind','50','50')
    filtered = filter_observed_speed(paired, 5)
    _, a, b = comparison_scores(filtered,'wind',15,probability_a=True,probability_b=True)
    assert a['n'] == b['n'] == a['n_prob'] == b['n_prob'] == 1
    assert a['brier_score'] == b['brier_score'] == 1
    assert direction_cases(filtered)[1]['missing_fields'] == ['a_forecast_direction','b_forecast_direction']


def comparison_page(tmp_path):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).parents[1]/'web_app/pages/4_Model_Comparison.py'), default_timeout=15).run()
    metadata = tmp_path/'stations.parquet'
    pd.DataFrame({'station_id':['A'],'latitude':[58.3],'longitude':[-134.5]}).to_parquet(metadata,index=False)
    app.text_input(key='compare_metadata').set_value(str(metadata))
    app.text_input(key='compare_archive_root').set_value(str(tmp_path))
    app.text_input(key='compare_stations').set_value('A')
    app.date_input(key='compare_start').set_value(date(2026,6,2))
    app.date_input(key='compare_end').set_value(date(2026,6,2))
    app.number_input(key='compare_obs_tolerance').set_value(15)
    app.checkbox(key='compare_use_offset').set_value(True)
    app.checkbox(key='compare_verify_direction').set_value(True)
    app.checkbox(key='compare_filter_speed').set_value(True).run()
    app.number_input(key='compare_offset').set_value(-6.)
    return app


def test_page_independent_speed_and_direction_filters_saved_context_and_empty_speed(tmp_path):
    archive_fixture(tmp_path)
    app = comparison_page(tmp_path)
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error
    result = app.session_state['comparison_result']
    assert len(result['cases']) == 1
    assert result['diagnostics']['cases_excluded_by_speed_minimum'] == 1
    assert len(result['direction_result']['cases']) == 1
    assert result['direction_result']['scores'].set_index('metric').loc['angular_mae','a'] == 20
    assert any('Direction metric' in frame.value.columns for frame in app.dataframe)
    app.number_input(key='compare_direction_min_cases').set_value(1)
    app.selectbox(key='compare_direction_display_metric').set_value('exceedance_percent').run()
    assert not app.exception
    app.number_input(key='compare_direction_threshold').set_value(180)
    app.number_input(key='compare_speed_minimum').set_value(15.).run()
    assert any('previous settings' in i.value for i in app.info)
    assert len(app.session_state['comparison_result']['cases']) == 1
    assert app.session_state['comparison_result']['context']['direction_error_threshold'] == 45
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error
    result = app.session_state['comparison_result']
    assert result['cases'].empty and len(result['direction_result']['cases']) == 1
    assert result['direction_result']['scores'].set_index('metric').loc['exceedance_percent','b'] == 0
    assert any('No cases remain for wind-speed' in w.value for w in app.warning)
    # Turning direction off and the speed filter off restores the original speed sample.
    app.checkbox(key='compare_verify_direction').set_value(False)
    app.checkbox(key='compare_filter_speed').set_value(False).run()
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and len(app.session_state['comparison_result']['cases']) == 2
    assert app.session_state['comparison_result']['direction_result'] is None


def test_page_missing_qmd_direction_keeps_filtered_speed_and_probabilities(tmp_path):
    archive_fixture(tmp_path)
    app = comparison_page(tmp_path)
    app.selectbox(key='compare_model_b').set_value('nbmqmd').run()
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error
    result = app.session_state['comparison_result']
    assert len(result['cases']) == 1 and result['summary_b']['n_prob'] == 1
    assert any('Wind direction verification is unavailable' in i.value for i in app.info)
    assert any('Only one model' in i.value for i in app.info)
    app.selectbox(key='compare_model_b').set_value('nbm').run()
    app.number_input(key='compare_direction_min_speed').set_value(100.)
    app.button(key='compare_run').click().run(timeout=30)
    assert not app.exception and not app.error
    result = app.session_state['comparison_result']
    assert len(result['cases']) == 1 and result['direction_result']['cases'].empty
    assert any('No shared cases remain for wind direction' in i.value for i in app.info)
    app.selectbox(key='compare_element').set_value('snow6hr').run()
    assert not app.exception
    assert not any(c.key == 'compare_verify_direction' for c in app.checkbox)
