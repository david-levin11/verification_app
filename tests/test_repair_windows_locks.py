"""Simulate Windows file-sharing failures without needing a Windows host."""
import json
from pathlib import Path
import sys
import pytest
import pandas as pd

sys.path.insert(0,str(Path(__file__).parents[1]))
import repair_local_interval_timestamps as repair_module


def locked():
    exc=PermissionError(13,'Access is denied')
    exc.winerror=5
    return exc


def test_transient_lock_keeps_old_manifest_until_atomic_replace(tmp_path,monkeypatch):
    path=tmp_path/'manifest.json'
    path.write_text('{"status":"INCOMPLETE"}')
    replace=Path.replace
    attempts=[];waits=[]
    def replace_with_lock(src,dst):
        attempts.append(src)
        if len(attempts)<3:
            assert json.loads(path.read_text())=={'status':'INCOMPLETE'}
            raise locked()
        return replace(src,dst)
    monkeypatch.setattr(Path,'replace',replace_with_lock)
    monkeypatch.setattr(repair_module.time,'sleep',waits.append)
    repair_module.save_json(path,{'status':'COMPLETE'})
    assert json.loads(path.read_text())=={'status':'COMPLETE'}
    assert waits==[.1,.2] and len(attempts)==3
    assert list(tmp_path.iterdir())==[path]


def test_persistent_lock_preserves_previous_journal_and_fails_bounded(tmp_path,monkeypatch):
    path=tmp_path/'installation.json';path.write_text('{"status":"PREPARING"}')
    waits=[]
    def deny(src,dst):raise locked()
    monkeypatch.setattr(Path,'replace',deny)
    monkeypatch.setattr(repair_module.time,'sleep',waits.append)
    with pytest.raises(PermissionError,match='after 10 attempts'):
        repair_module.save_json(path,{'status':'INSTALLED'})
    assert len(waits)==9 and sum(waits)<10
    assert json.loads(path.read_text())=={'status':'PREPARING'}
    assert list(tmp_path.iterdir())==[path]


def test_unrelated_io_errors_are_not_retried(tmp_path,monkeypatch):
    waits=[]
    def fail(src,dst):raise OSError(28,'No space left on device')
    monkeypatch.setattr(Path,'replace',fail)
    monkeypatch.setattr(repair_module.time,'sleep',waits.append)
    with pytest.raises(OSError,match='No space'):
        repair_module.save_json(tmp_path/'manifest.json',{})
    assert not waits


def test_staging_lock_failure_leaves_archives_unchanged_and_can_retry(tmp_path,monkeypatch):
    source=tmp_path/'model';folder=source/'nbmqmd/maxt';folder.mkdir(parents=True)
    p=folder/'2025_06_archive.parquet'
    pd.DataFrame({'station_id':['A'],'init_time':[pd.Timestamp('2025-06-14 06:00')],
        'valid_time':[pd.Timestamp('2025-06-17 12:00')],'forecast_hour':[78],
        'maxt_p50':[50.]}).to_parquet(p,index=False)
    original=p.read_bytes()
    replace=Path.replace
    def deny_manifest_updates(src,dst):
        if Path(dst).name=='manifest.json' and Path(dst).exists():raise locked()
        return replace(src,dst)
    monkeypatch.setattr(Path,'replace',deny_manifest_updates)
    monkeypatch.setattr(repair_module.time,'sleep',lambda seconds:None)
    with pytest.raises(PermissionError,match='after 10 attempts'):
        repair_module.repair_in_place(source)
    assert p.read_bytes()==original
    assert not (source/repair_module.STATE_FILE).exists()
    journal=next(tmp_path.glob('model_timestamp_backup_*/installation.json'))
    assert json.loads(journal.read_text())['status']=='ROLLED_BACK'
    monkeypatch.setattr(Path,'replace',replace)
    backup=repair_module.repair_in_place(source)
    assert (backup/'originals/nbmqmd/maxt/2025_06_archive.parquet').read_bytes()==original
    result=pd.read_parquet(p)
    assert result.init_time.iloc[0]==pd.Timestamp('2025-06-15')
