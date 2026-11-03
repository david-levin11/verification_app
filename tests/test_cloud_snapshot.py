"""Cloud deployment uses bounded streamed snapshots and preserves local defaults."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import zipfile
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from cloud_snapshot import prepare_snapshot,extract_snapshot,SnapshotError,inspect_snapshot
from test_nbm_deterministic import archive_fixture


class Response:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def raise_for_status(self):pass
    def iter_content(self,chunk_size):
        for start in range(0,len(self.data),97):yield self.data[start:start+97]


class Download:
    def __init__(self,data):self.data=data;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        assert kwargs['stream'] is True
        return Response(self.data)


def snapshot(tmp_path,wrapper=''):
    folder=tmp_path/'source';root=folder/wrapper;root.mkdir(parents=True)
    archive_fixture(root/'model','wind')
    (root/'metadata').mkdir()
    (root/'model/metadata.parquet').rename(root/'metadata/ak_station_metadata.parquet')
    (root/'derived/refs').mkdir(parents=True)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as output:
        for path in folder.rglob('*'):
            if path.is_file():output.write(path,path.relative_to(folder))
    data=stream.getvalue()
    settings=dict(archive_url='https://example.test/snapshot-v1.zip',archive_sha256=hashlib.sha256(data).hexdigest(),
                  snapshot_id='v1',cache_dir=str(tmp_path/'cache'))
    return settings,Download(data)


@pytest.mark.parametrize('wrapper',['','verification-test-data'])
def test_snapshot_auto_paths_dates_runs_and_reuse(tmp_path,wrapper):
    settings,download=snapshot(tmp_path,wrapper)
    result=prepare_snapshot(settings,session=download)
    assert len(download.calls)==1
    assert Path(result['model_root']).is_dir() and Path(result['metadata_path']).is_file()
    assert result['model']=='nbmqmd' and result['element']=='wind'
    assert result['start_date']=='2026-06-30' and result['end_date']=='2026-06-30'
    assert result['init_time']=='2026-06-29 00:00:00'
    assert set(result['stations'])=={'A','B'}
    assert result['comparison_model']=='nbm'
    assert prepare_snapshot(settings,session=download)==result
    assert len(download.calls)==1
    # An evicted complete cache can be rebuilt using the original asset.
    import shutil
    shutil.rmtree(Path(result['model_root']).parents[0])
    rebuilt=prepare_snapshot(settings,session=download)
    assert Path(rebuilt['metadata_path']).is_file() and len(download.calls)==2


def test_digest_failure_is_not_published_and_can_retry(tmp_path):
    settings,download=snapshot(tmp_path)
    broken=Download(b'partial download')
    with pytest.raises(SnapshotError,match='SHA-256'):prepare_snapshot(settings,session=broken)
    assert not list((tmp_path/'cache').rglob('snapshot-ready.json'))
    assert not list((tmp_path/'cache').glob('snapshot-*'))
    assert prepare_snapshot(settings,session=download)['model']=='nbmqmd'


def test_concurrent_sessions_download_only_once(tmp_path):
    settings,download=snapshot(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(lambda _:prepare_snapshot(settings,session=download),range(2)))
    assert results[0]==results[1] and len(download.calls)==1


@pytest.mark.parametrize('name',['../escape','/absolute','C:/windows','folder/../../escape','..\\escape'])
def test_zip_paths_cannot_escape(tmp_path,name):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as output:output.writestr(name,'bad')
    with pytest.raises(SnapshotError):extract_snapshot(path,tmp_path/'out')
    assert not (tmp_path/'escape').exists()


def test_links_duplicates_and_expansion_limit_rejected(tmp_path):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as output:
        info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        output.writestr(info,'target')
    with pytest.raises(SnapshotError,match='symbolic'):extract_snapshot(path,tmp_path/'out')
    with zipfile.ZipFile(path,'w') as output:output.writestr('large','x'*100)
    with pytest.raises(SnapshotError,match='limit'):extract_snapshot(path,tmp_path/'out',max_bytes=10)


def test_private_token_only_sent_to_github_api(tmp_path):
    settings,download=snapshot(tmp_path)
    with pytest.raises(SnapshotError,match='API URL'):prepare_snapshot(settings,token='secret',session=download)
    settings['archive_url']='https://api.github.com/repos/owner/data/releases/assets/123'
    prepare_snapshot(settings,token='secret',session=download)
    assert download.calls[-1][1]['headers']['Authorization']=='Bearer secret'


def test_cloud_defaults_apply_on_direct_pages_and_do_not_override_user_edits(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import cloud_runtime,storm_visuals
    settings,download=snapshot(tmp_path)
    context=prepare_snapshot(settings,session=download)
    from concurrent.futures import Future
    from types import SimpleNamespace
    ready=Future();ready.set_result(context)
    monkeypatch.setattr(cloud_runtime,'_snapshot_job',lambda *args,**kwargs:SimpleNamespace(future=ready))
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kwargs:None)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20)
    app.secrets['cloud']={'enabled':True,'archive_url':settings['archive_url'],'archive_sha256':settings['archive_sha256']}
    app.run()
    assert not app.exception
    for page in ['map','aggregate','storm','compare']:
        file={'map':'1_Map_Explorer','aggregate':'2_Aggregate_Verification','storm':'3_Storm_Zoom','compare':'4_Model_Comparison'}[page]
        app.switch_page(f'pages/{file}.py').run()
        assert not app.exception and not app.error,[x.value for x in app.exception]+[x.value for x in app.error]
        key={'map':'map_ui_archive_root','aggregate':'aggregate_ui_archive_root','storm':'storm_Local Archive Root','compare':'compare_archive_root'}[page]
        assert app.text_input(key=key).value==context['model_root']
        datekey={'map':'map_ui_start_date','aggregate':'aggregate_ui_start_date','storm':'storm_Plot Start Date','compare':'compare_start'}[page]
        assert app.date_input(key=datekey).value==date(2026,6,30)
        button={'map':'Build Station Metric Map','aggregate':'Run Aggregate Verification',
                'storm':'Generate Storm Timeseries','compare':'Run Model Comparison'}[page]
        next(b for b in app.button if b.label==button).click().run(timeout=30)
        assert not app.exception and not app.error,[x.value for x in app.exception]+[x.value for x in app.error]
        if page=='map':assert app.session_state['station_metrics'].n.sum()==4
        elif page=='aggregate':assert app.session_state['aggregate_summary']['n']==4
        elif page=='storm':assert len(app.session_state['storm_result']['cases'])==4
        else:assert len(app.session_state['comparison_result']['cases'])==4
    app.date_input(key='compare_start').set_value(date(2026,6,29)).run()
    assert app.date_input(key='compare_start').value==date(2026,6,29)
    app.switch_page('pages/1_Map_Explorer.py').run()
    app.switch_page('pages/4_Model_Comparison.py').run()
    assert app.date_input(key='compare_start').value==date(2026,6,29)


def test_disabled_cloud_leaves_existing_local_defaults_untouched(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import cloud_runtime
    def forbidden(*args,**kwargs):raise AssertionError('Local mode must not download a snapshot')
    monkeypatch.setattr(cloud_runtime,'_snapshot_job',forbidden)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py')).run()
    assert not app.exception
    app.switch_page('pages/3_Storm_Zoom.py').run()
    assert app.text_input(key='storm_Local Archive Root').value=='../model'
    assert app.date_input(key='storm_Plot Start Date').value==date(2026,2,21)


def test_background_preparation_does_not_block_page_and_resumes(tmp_path,monkeypatch):
    from threading import Event
    from streamlit.testing.v1 import AppTest
    import cloud_runtime
    settings,download=snapshot(tmp_path)
    context=prepare_snapshot(settings,session=download)
    release=Event();started=Event();calls=[]
    def slow_prepare(settings,token=None,progress=None):
        calls.append(settings);progress('Downloading archive: 32 MiB received')
        started.set()
        if not release.wait(10):raise RuntimeError('Test worker was not released')
        return context
    monkeypatch.setattr(cloud_runtime,'prepare_snapshot',slow_prepare)
    cloud_runtime._snapshot_job.clear()
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=3)
    app.secrets['cloud']={'enabled':True,'archive_url':'https://example.com/slow.zip'}
    try:
        app.run()
        assert started.wait(1)
        assert not app.exception and len(calls)==1
        assert 'Preparing the test archive' in app.info[0].value
        app.run()
        assert len(calls)==1
    finally:release.set()
    identity=json.dumps(dict(app.secrets['cloud']),sort_keys=True,default=str)
    cloud_runtime._snapshot_job(identity).future.result(timeout=3)
    app.run()
    assert not app.exception and 'Test snapshot:' in app.info[0].value
    cloud_runtime._snapshot_job.clear()


def test_background_failure_shows_retry_and_restarts(monkeypatch):
    from concurrent.futures import Future
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest
    import cloud_runtime
    failed=Future();failed.set_exception(SnapshotError('Digest mismatch'))
    pending=Future()
    class Jobs:
        def __init__(self):self.cleared=False
        def __call__(self,*args,**kwargs):
            return SimpleNamespace(future=pending,status=lambda:'Downloading') if self.cleared else SimpleNamespace(future=failed)
        def clear(self):self.cleared=True
    jobs=Jobs();monkeypatch.setattr(cloud_runtime,'_snapshot_job',jobs)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'))
    app.secrets['cloud']={'enabled':True}
    app.run()
    assert 'Digest mismatch' in app.error[0].value
    app.button(key='cloud_retry').click().run()
    assert jobs.cleared and not app.exception and not app.error
    assert 'Preparing the test archive' in app.info[0].value


def test_real_health_check_returns_before_snapshot_finishes(tmp_path):
    """Exercise the same script-health endpoint used by Community Cloud."""
    import os
    import socket
    import subprocess
    import time
    import requests
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    worker_started=tmp_path/'worker-started'
    app=tmp_path/'slow_app.py'
    app.write_text(f'''
import sys,time
from pathlib import Path
sys.path.insert(0,{str(Path(__file__).parents[1]/'web_app')!r})
import streamlit as st
import cloud_runtime
st.set_page_config(page_title='Startup test')
def prepare(*args,**kwargs):
    Path({str(worker_started)!r}).touch()
    time.sleep(120)
cloud_runtime.prepare_snapshot=prepare
cloud_runtime.cloud_settings=lambda: {{'enabled':True,'archive_url':'https://example.com/slow.zip'}}
cloud_runtime.cloud_context()
''')
    with (tmp_path/'server.log').open('w+') as log:
        process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(app),
            '--server.headless=true','--server.fileWatcherType=none',f'--server.port={port}',
            '--server.scriptHealthCheckEnabled=true','--browser.gatherUsageStats=false'],
            stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ))
        try:
            deadline=time.monotonic()+30
            while True:
                try:
                    response=requests.get(f'http://127.0.0.1:{port}/_stcore/health',timeout=1)
                    if response.ok:break
                except requests.RequestException:pass
                assert time.monotonic()<deadline,'Streamlit did not start'
                time.sleep(.1)
            before=time.monotonic()
            response=requests.get(f'http://127.0.0.1:{port}/_stcore/script-health-check',timeout=20)
            assert response.status_code==200,response.text
            assert response.text=='ok' and worker_started.is_file()
            assert time.monotonic()-before<20
            # A second health-check session must reuse the ongoing preparation.
            assert requests.get(f'http://127.0.0.1:{port}/_stcore/script-health-check',timeout=5).status_code==200
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
