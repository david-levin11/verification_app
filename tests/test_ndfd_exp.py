"""Experimental forecasts use archived cycles and match only compatible periods."""
from datetime import date
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'web_app'))
from archive_availability import coverage, missing_ranges
from comparison import comparison_cases
from comparison_loader import load_comparison_data
from config import get_available_obs_sources
from data_loader import fetch_data
from pairing import build_verification_pairs


def write_archive(root, model, element, month, rows):
    folder = root / model / element
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(folder / f'{month}_archive.parquet', index=False)


def exp_row(init, valid, **values):
    init, valid = pd.Timestamp(init), pd.Timestamp(valid)
    return dict(station_id='A', init_time=init, valid_time=valid,
                forecast_hour=(valid - init).total_seconds() / 3600,
                initialization_offset_hours=72, **values)


def wind_archives(root):
    rows = [exp_row('2026-05-30', '2026-06-08', wind_speed_kt=11),
            exp_row('2026-06-07', '2026-06-14', wind_speed_kt=12)]
    for month, row in zip(('2026_05', '2026_06'), rows):
        write_archive(root, 'ndfd_exp', 'wind', month, [row])
    for model in ('ndfd', 'nbm'):
        for month, row in zip(('2026_05', '2026_06'), rows):
            source = row.copy()
            if model == 'nbm':
                source['init_time'] -= pd.Timedelta(hours=5)
                source['forecast_hour'] += 5
            else:
                del source['init_time']
            write_archive(root, model, 'wind', month, [source])
    write_archive(root, 'obs', 'wind', '2026_06', [
        dict(stid='A', valid_time=row['valid_time'] - pd.Timedelta(minutes=7),
             obs_wind_speed_kts=10) for row in rows
    ])


def test_sparse_coverage_and_comparisons_use_archived_cycles(tmp_path):
    wind_archives(tmp_path)
    start, end = date(2026, 6, 8), date(2026, 6, 14)
    assert missing_ranges(coverage(tmp_path, 'ndfd_exp', 'wind'), start, end) == [
        (pd.Timestamp('2026-06-09'), pd.Timestamp('2026-06-13'))
    ]
    forecast, observations, _ = fetch_data(
        'Aggregate Verification', 'ndfd_exp', 'obs', start, end, ['A'], [], None, {}, None,
        archive_root=tmp_path,
    )
    assert sorted(forecast.forecast_hour) == [168, 216]
    assert len(build_verification_pairs(forecast, observations, 'ndfd_exp', 'obs', 'wind')) == 2
    for other, offset in [('ndfd', 0), ('nbm', -5)]:
        a, b, obs, _ = load_comparison_data(
            tmp_path, 'ndfd_exp', other, 'obs', 'wind', start, end, ['A'], lookback_hours=250
        )
        cases, _ = comparison_cases(a, b, obs, 'ndfd_exp', other, 'wind',
                                    lead_max=250, offset_hours=offset)
        assert sorted(cases.a_forecast_hour) == [168, 216]
        assert set(cases.actual_offset_hours) == {offset}
        assert set(cases.obs_time_offset_minutes) == {-7}
        assert pd.Timestamp('2026-05-30') in set(cases.a_init_time)


def test_experimental_maximum_matches_exact_window_across_endpoint_month(tmp_path):
    start, end = pd.Timestamp('2026-05-31 12:00'), pd.Timestamp('2026-06-01')
    forecast = exp_row('2026-05-27', end, maxt=55., window_start=start, window_end=end)
    obs = dict(stid='A', valid_time=end, window_start=start, window_end=end,
               tmax=54., coverage_ok=True)
    write_archive(tmp_path, 'ndfd_exp', 'maxt', '2026_05', [forecast])
    write_archive(tmp_path, 'obs_12hr', 'maxt', '2026_06', [
        obs, dict(obs, window_start=start + pd.Timedelta(hours=1), tmax=90.),
        dict(obs, coverage_ok=False, tmax=99.),
    ])
    day = date(2026, 5, 31)
    f, o, _ = fetch_data('Aggregate Verification', 'ndfd_exp', 'obs_12hr', day, day, ['A'],
                         [], None, {}, None, element='maxt', archive_root=tmp_path)
    pairs = build_verification_pairs(f, o, 'ndfd_exp', 'obs_12hr', 'maxt')
    assert pairs.obs_value.tolist() == [54.]
    assert pairs.obs_window_start.tolist() == [start]
    assert pairs.obs_window_end.tolist() == [end]
    assert pairs.pair_date.tolist() == [day]
    assert coverage(tmp_path, 'obs_12hr', 'maxt').spans == [(pd.Timestamp(day), pd.Timestamp(day))]
    assert get_available_obs_sources('maxt', 'ndfd_exp', 'nbm') == []
    with pytest.raises(ValueError, match='same verification window'):
        load_comparison_data(tmp_path, 'ndfd_exp', 'nbm', 'obs_12hr', 'maxt', day, day, ['A'])


def test_experimental_old_cycle_ingest_requires_repair(tmp_path):
    row = dict(exp_row('2026-05-30', '2026-06-08', wind_speed_kt=11), initialization_offset_hours=84)
    write_archive(tmp_path, 'ndfd_exp', 'wind', '2026_05', [row])
    write_archive(tmp_path, 'obs', 'wind', '2026_06', [
        dict(stid='A', valid_time=pd.Timestamp('2026-06-08'), obs_wind_speed_kts=10.)
    ])
    day = date(2026, 6, 8)
    with pytest.raises(ValueError, match='72-hour initialization repair'):
        load_comparison_data(tmp_path, 'ndfd_exp', 'ndfd_exp', 'obs', 'wind', day, day, ['A'])


def test_model_comparison_page_runs_across_experimental_gaps(tmp_path):
    from streamlit.testing.v1 import AppTest

    wind_archives(tmp_path)
    page = Path(__file__).parents[1] / 'web_app' / 'pages' / '4_Model_Comparison.py'
    app = AppTest.from_file(str(page), default_timeout=20)
    app.secrets['local'] = dict(archive_root=str(tmp_path))
    app.run()
    app.selectbox(key='compare_model_a').set_value('ndfd_exp').run()
    assert not app.exception
    assert 'maxt' in app.selectbox(key='compare_element').options
    app.selectbox(key='compare_element').set_value('wind').run()
    app.text_input(key='compare_stations').set_value('A')
    app.date_input(key='compare_start').set_value(date(2026, 6, 8))
    app.date_input(key='compare_end').set_value(date(2026, 6, 14))
    app.checkbox(key='compare_use_offset').set_value(True).run()
    app.number_input(key='compare_offset').set_value(-5.)
    assert app.checkbox(key='compare_all_ndfd_exp').value
    app.button(key='compare_run').click().run()
    assert not app.exception and not app.error
    assert any('part of your date range' in w.value for w in app.warning)
    cases = app.session_state['comparison_result']['cases']
    assert sorted(cases.a_forecast_hour) == [168, 216]
    assert set(cases.actual_offset_hours) == {-5}


def test_native_extrema_keep_distinct_windows_with_the_same_endpoint(tmp_path):
    end = pd.Timestamp('2026-06-02 05:00')
    starts = [end - pd.Timedelta(hours=hours) for hours in (15, 10, 9)]
    forecasts = [
        exp_row('2026-05-29', end, maxt=forecast, window_start=start, window_end=end)
        for forecast, start in zip((50, 60, 90), starts)
    ]
    obs = [
        dict(stid='A', window_start=start, window_end=end, valid_time=end,
             tmax=value, coverage_ok=covered)
        for start, value, covered in zip(starts, (49, 59, 12), (True, True, False))
    ]
    write_archive(tmp_path, 'ndfd_exp', 'maxt_native', '2026_05', forecasts)
    write_archive(tmp_path, 'obs_exp', 'maxt', '2026_06', obs)
    day = date(2026, 6, 2)
    assert coverage(tmp_path, 'obs_exp', 'maxt_native').spans == [(pd.Timestamp(day), pd.Timestamp(day))]
    f, o, _ = fetch_data('Aggregate Verification', 'ndfd_exp', 'obs_exp', day, day, ['A'],
                         [], None, {}, None, element='maxt_native', archive_root=tmp_path)
    pairs = build_verification_pairs(f, o, 'ndfd_exp', 'obs_exp', 'maxt_native')
    assert sorted(zip(pairs.model_value, pairs.obs_value)) == [(50, 49), (60, 59)]
    assert pairs.model_window_start.eq(pairs.obs_window_start).all()
    assert pairs.model_window_end.eq(pairs.obs_window_end).all()


def test_experimental_minrh_comparison_scores_the_shared_12hour_window():
    end = pd.Timestamp('2026-06-10 06:00')
    start = end - pd.Timedelta(hours=12)
    a = pd.DataFrame([exp_row('2026-06-06', end, minrh=25., window_start=start, window_end=end)])
    b = pd.DataFrame([exp_row('2026-06-06', end, minrh=28.)])
    o = pd.DataFrame([
        dict(stid='A', valid_time=end, window_start=start, window_end=end, minrh=30., coverage_ok=True),
        dict(stid='A', valid_time=end, window_start=start - pd.Timedelta(hours=6),
             window_end=end, minrh=1., coverage_ok=True),
    ])
    pairs, _ = comparison_cases(a, b, o, 'ndfd_exp', 'nbm', 'minrh', obs_source='obs_12hr')
    assert pairs.obs_value.tolist() == [30.]
    assert pairs.obs_window_start.tolist() == [start]
    assert pairs.obs_window_end.tolist() == [end]


@pytest.mark.parametrize('other', ['ndfd', 'nbm'])
@pytest.mark.parametrize('source', ['obs', 'obs_12hr', 'obs_exp'])
def test_date_aligned_maxt_crosses_month_and_shares_one_observation(tmp_path, other, source):
    day = date(2026, 5, 31)
    start = pd.Timestamp('2026-05-31 12:00')
    end = pd.Timestamp('2026-06-01')
    exp = exp_row('2026-05-27', end, maxt=55., window_start=start, window_end=end)
    if other == 'ndfd':
        ordinary = dict(station_id='A', forecast_hour=108, maxt=51., valid_time=start)
    else:
        ordinary = exp_row('2026-05-27', '2026-06-01 06:00', maxt=51.)
    write_archive(tmp_path, 'ndfd_exp', 'maxt', '2026_05', [exp])
    write_archive(tmp_path, other, 'maxt', '2026_05', [ordinary])

    if source == 'obs':
        obs = dict(stid='A', date=pd.Timestamp(day), window_start=start,
                   window_end=end + pd.Timedelta(hours=6), tmax=54.)
        write_archive(tmp_path, source, 'maxt', '2026_05', [obs])
    else:
        nominal_start = start + pd.Timedelta(hours=2) if source == 'obs_exp' else start
        nominal_end = end + pd.Timedelta(hours=5) if source == 'obs_exp' else end
        obs = dict(stid='A', window_start=nominal_start, window_end=nominal_end, tmax=54., coverage_ok=True)
        longer = dict(obs, window_end=nominal_end + pd.Timedelta(hours=1), tmax=93.)
        write_archive(tmp_path, source, 'maxt', '2026_06', [longer, obs] if source == 'obs_exp' else [obs])
    a, b, o, _ = load_comparison_data(tmp_path, 'ndfd_exp', other, source, 'maxt', day, day, ['A'],
                                       align_by_date=True)
    pairs, _ = comparison_cases(a, b, o, 'ndfd_exp', other, 'maxt', obs_source=source, align_by_date=True)
    reversed_pairs, _ = comparison_cases(b, a, o, other, 'ndfd_exp', 'maxt',
                                         obs_source=source, align_by_date=True)
    assert pairs.target_time.tolist() == [pd.Timestamp(day)]
    assert pairs.obs_value.tolist() == reversed_pairs.obs_value.tolist() == [54.]
    assert pairs.obs_source.tolist() == [source]
    assert pairs.a_window_end.tolist() == [end]
    assert pairs.obs_window_end.tolist() == [obs['window_end']]
    if other == 'ndfd' and source == 'obs_exp':
        from streamlit.testing.v1 import AppTest

        page = Path(__file__).parents[1] / 'web_app' / 'pages' / '4_Model_Comparison.py'
        app = AppTest.from_file(str(page), default_timeout=20)
        app.secrets['local'] = dict(archive_root=str(tmp_path))
        app.run()
        app.selectbox(key='compare_model_a').set_value('ndfd_exp')
        app.selectbox(key='compare_model_b').set_value('ndfd').run()
        app.selectbox(key='compare_element').set_value('maxt').run()
        assert app.selectbox(key='compare_period_mode_maxt').value == 'Align by verification date'
        assert app.selectbox(key='compare_obs_maxt').options == ['obs', 'obs_exp', 'obs_12hr']
        app.selectbox(key='compare_obs_maxt').set_value('obs_exp').run()
        app.text_input(key='compare_stations').set_value('A')
        app.date_input(key='compare_start').set_value(day)
        app.date_input(key='compare_end').set_value(day)
        app.button(key='compare_run').click().run()
        assert not app.exception and not app.error
        assert not any(widget.key == 'compare_obs_tolerance' for widget in app.number_input)
        saved = app.session_state['comparison_result']
        assert saved['context']['align_by_date']
        assert saved['cases'].obs_value.tolist() == [54.]



@pytest.mark.parametrize(('element', 'experimental_end', 'other_end', 'obs_end'), [
    ('mint', '2026-06-02 12:00', '2026-06-02 18:00', '2026-06-02 20:00'),
    ('minrh', '2026-06-02 06:00', '2026-06-02 05:00', '2026-06-02 06:00'),
])
def test_date_alignment_allows_different_mint_and_minrh_endpoints(element, experimental_end, other_end, obs_end):
    exp_end, op_end, obs_end = map(pd.Timestamp, (experimental_end, other_end, obs_end))
    exp = exp_row('2026-06-01', exp_end, **{element: 25.},
                  window_start=exp_end-pd.Timedelta(hours=12), window_end=exp_end)
    op = dict(station_id='A', valid_time=op_end, window_end=op_end,
              window_start=op_end-pd.Timedelta(hours=18), **{element: 28.},
              forecast_hour=(op_end-pd.Timestamp('2026-06-01')).total_seconds() / 3600)
    obs = dict(stid='A', window_end=obs_end, window_start=obs_end-pd.Timedelta(hours=18),
               coverage_ok=True, **{element: 29.})
    pairs, _ = comparison_cases(pd.DataFrame([exp]), pd.DataFrame([op]), pd.DataFrame([obs]),
                               'ndfd_exp', 'ndfd', element, obs_source='obs_exp', align_by_date=True)
    assert pairs.obs_value.tolist() == [29.]
    assert pairs.a_window_end.tolist() == [exp_end]
    assert pairs.b_window_end.tolist() == [op_end]
    assert pairs.obs_window_end.tolist() == [obs_end]
