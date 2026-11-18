"""Archive-aware defaults, honest coverage warnings, and graphics-only outputs."""
from pathlib import Path
from datetime import date
import sys
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from archive_availability import coverage, latest_dates, missing_ranges, preflight, Coverage


def archive(root,model,month,times,column=None,statistics=True):
    folder=root/model/'wind';folder.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame({'station_id':['A']*len(times),'valid_time':pd.to_datetime(times),
        column or ('obs_wind_speed_kts' if model=='obs' else 'wind_speed_kt'):10.})
    if model=='obs':frame=frame.rename(columns={'station_id':'stid'})
    if model!='obs':
        frame['init_time']=frame.valid_time-pd.Timedelta(hours=6);frame['forecast_hour']=6
    pq.write_table(pa.Table.from_pandas(frame),folder/f'{month}_archive.parquet',write_statistics=statistics)


def test_footer_only_dates_defaults_and_missing_intervals(tmp_path,monkeypatch):
    archive(tmp_path,'nbm','2026_05',['2026-05-08 06:00','2026-05-31 18:00'])
    archive(tmp_path,'obs','2026_05',['2026-05-09','2026-05-30'])
    monkeypatch.setattr(pd,'read_parquet',lambda *a,**k:pytest.fail('Coverage must not load archive rows'))
    m,o=[coverage(tmp_path,name,'wind') for name in ['nbm','obs']]
    assert latest_dates([m,o])==(date(2026,5,9),date(2026,5,30))
    assert missing_ranges(m,date(2026,5,1),date(2026,6,2))==[
        (pd.Timestamp('2026-05-01'),pd.Timestamp('2026-05-07')),
        (pd.Timestamp('2026-06-01'),pd.Timestamp('2026-06-02'))]
    # Appended/replaced files invalidate footer results by size/mtime.
    archive(tmp_path,'nbm','2026_05',['2026-05-01','2026-05-31'])
    assert coverage(tmp_path,'nbm','wind').spans[0][0]==pd.Timestamp('2026-05-01')


def test_gaps_wrong_element_and_unknown_footer_statistics(tmp_path):
    archive(tmp_path,'nbm','2026_05',['2026-05-01','2026-05-31'])
    archive(tmp_path,'nbm','2026_07',['2026-07-01','2026-07-31'])
    result=coverage(tmp_path,'nbm','wind')
    assert missing_ranges(result,date(2026,5,1),date(2026,7,31))==[
        (pd.Timestamp('2026-06-01'),pd.Timestamp('2026-06-30'))]
    folder=tmp_path/'nbm/precip6hr';folder.mkdir()
    pd.DataFrame({'station_id':['A'],'valid_time':[pd.Timestamp('2026-07-01')],
                  'maxt':[60.]}).to_parquet(folder/'2026_07_archive.parquet')
    wrong=coverage(tmp_path,'nbm','precip6hr')
    assert not wrong.spans and 'contains maxt' in wrong.issues[0]
    archive(tmp_path,'hrrr','2026_07',['2026-07-05'],statistics=False)
    unknown=coverage(tmp_path,'hrrr','wind')
    assert unknown.unknown and unknown.spans==[(pd.Timestamp('2026-07-01'),pd.Timestamp('2026-07-31'))]


def test_individual_ranges_without_common_dates_are_not_runnable():
    class Messages:
        def __init__(self):self.messages=[]
        def warning(self,text):self.messages.append(text)
        def caption(self,text):pass
        def error(self,text):self.messages.append(text)
    messages=Messages()
    model=Coverage('nbm','wind',[(pd.Timestamp('2026-05-01'),pd.Timestamp('2026-05-31'))])
    obs=Coverage('obs','wind',[(pd.Timestamp('2026-06-01'),pd.Timestamp('2026-06-30'))])
    assert not preflight([model,obs],date(2026,5,1),date(2026,6,30),messages)
    assert any('no overlapping archive dates' in message for message in messages.messages)


def test_gust_fallback_refs_root_and_daily_temperature_target_dates(tmp_path):
    archive(tmp_path,'nbm','2026_05',['2026-05-01','2026-05-31'],column='wind_gust_kt')
    assert coverage(tmp_path,'nbm','gust').spans
    derived=tmp_path/'separate/refs/wind';derived.mkdir(parents=True)
    pd.DataFrame({'valid_time':pd.to_datetime(['2026-05-01','2026-05-31']),
                  'p50':[10.,20.]}).to_parquet(derived/'2026_05_archive.parquet')
    assert coverage(tmp_path,'refs','wind',tmp_path/'separate/refs').spans
    folder=tmp_path/'nbm/maxt';folder.mkdir()
    pd.DataFrame({'valid_time':pd.to_datetime(['2026-06-01 06:00','2026-07-01 06:00']),
                  'maxt':[60.,70.]}).to_parquet(folder/'2026_06_archive.parquet')
    assert coverage(tmp_path,'nbm','maxt').spans==[(pd.Timestamp('2026-05-31'),pd.Timestamp('2026-06-30'))]


def app_with_archives(root):
    from streamlit.testing.v1 import AppTest
    archive(root,'nbm','2026_05',['2026-05-08 06:00','2026-05-31 18:00'])
    archive(root,'ndfd','2026_06',['2026-06-01 06:00','2026-06-30 18:00'])
    archive(root,'obs','2026_05',['2026-05-08 05:53','2026-05-31 17:53'])
    archive(root,'obs','2026_06',['2026-06-01 05:53','2026-06-30 17:53'])
    metadata=root/'stations.parquet'
    pd.DataFrame({'station_id':['A'],'latitude':[58.],'longitude':[-135.]}).to_parquet(metadata)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'))
    app.secrets['local']={'archive_root':str(root),'metadata_path':str(metadata)}
    return app.run().switch_page('pages/1_Map_Explorer.py').run()


def test_page_defaults_plain_language_preflight_and_user_date_preservation(tmp_path):
    app=app_with_archives(tmp_path)
    assert not app.exception and not app.dataframe
    assert app.date_input(key='map_ui_start_date').value==date(2026,5,8)
    assert app.date_input(key='map_ui_end_date').value==date(2026,5,31)
    app.selectbox(key='map_ui_model').set_value('ndfd').run()
    assert app.date_input(key='map_ui_start_date').value==date(2026,6,1)
    app.date_input(key='map_ui_start_date').set_value(date(2025,5,1))
    app.date_input(key='map_ui_end_date').set_value(date(2025,6,30)).run()
    assert not app.exception
    assert any('No NDFD Wind' in w.value and 'Available dates' in w.value for w in app.warning)
    assert next(b for b in app.button if b.label=='Build Station Metric Map').disabled
    app.selectbox(key='map_ui_model').set_value('nbm').run()
    assert app.date_input(key='map_ui_start_date').value==date(2025,5,1)
    app.date_input(key='map_ui_start_date').set_value(date(2026,5,1))
    app.date_input(key='map_ui_end_date').set_value(date(2026,5,31)).run()
    assert any('part of your date range' in w.value for w in app.warning)
    assert not next(b for b in app.button if b.label=='Build Station Metric Map').disabled


def test_successful_outputs_have_downloads_and_graphics_but_no_inline_tables(tmp_path):
    app=app_with_archives(tmp_path)
    next(b for b in app.button if b.label=='Build Station Metric Map').click().run()
    assert not app.exception and not app.dataframe and not app.json
    assert app.session_state['station_metrics'].n.sum()==2
    labels=[b.proto.label for b in app.get('download_button')]
    assert 'Download Station metrics (CSV)' in labels
    assert 'Download Station coverage (CSV)' in labels
    assert any(e.label=='Downloads — tables and diagnostics' for e in app.expander)
