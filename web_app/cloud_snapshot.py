"""Versioned, read-only test snapshots; independent of Streamlit and local paths."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from urllib.parse import urlparse
import zipfile
import duckdb
from filelock import FileLock
import pandas as pd
import requests
from config import MODELS, get_available_elements, get_element_config, get_obs_filter_time_column
from forecast_archive import register_forecast_archive
from forecast_targets import forecast_target_sql
from pairing import get_model_value_column, get_obs_value_column


class SnapshotError(ValueError):
    pass


def inside(root,relative):
    path=PurePosixPath(str(relative).replace('\\','/'))
    if path.is_absolute() or '..' in path.parts or any(':' in part for part in path.parts):
        raise SnapshotError('Archive paths must remain inside the snapshot.')
    return root.joinpath(*path.parts)


def extract_snapshot(archive,destination,max_bytes=20*1024**3,progress=None):
    """Reject escaping paths, links and duplicate files before extracting."""
    with zipfile.ZipFile(archive) as source:
        members=source.infolist()
        if sum(m.file_size for m in members)>max_bytes:
            raise SnapshotError('Expanded snapshot exceeds the configured extraction limit.')
        seen=set()
        for item in members:
            target=inside(destination,item.filename)
            if stat.S_ISLNK(item.external_attr>>16):raise SnapshotError('Snapshot ZIP must not contain symbolic links.')
            if not item.is_dir() and target in seen:raise SnapshotError('Snapshot ZIP contains duplicate file paths.')
            seen.add(target)
        for index,item in enumerate(members):
            if progress and index%100==0:progress(f'Extracting archive: {index:,} of {len(members):,} files')
            target=inside(destination,item.filename)
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with source.open(item) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1024**2)


def download_snapshot(url,target,expected_sha256,token=None,session=None,max_bytes=4*1024**3,progress=None):
    if urlparse(url).scheme!='https':raise SnapshotError('The snapshot download URL must use HTTPS.')
    headers={'User-Agent':'alaska-verification-cloud-test'}
    if token:
        if urlparse(url).netloc!='api.github.com':
            raise SnapshotError('Authenticated downloads require a GitHub release-asset API URL.')
        headers.update(Authorization=f'Bearer {token}',Accept='application/octet-stream')
    client=session or requests
    digest=hashlib.sha256();size=0;reported=0
    if progress:progress('Downloading the versioned archive…')
    # Stream to disk: the 1.5 GB ZIP must never be held in RAM.
    with client.get(url,headers=headers,stream=True,timeout=(20,120)) as response:
        response.raise_for_status()
        with Path(target).open('wb') as output:
            for chunk in response.iter_content(chunk_size=4*1024**2):
                if not chunk:continue
                size+=len(chunk)
                if size>max_bytes:raise SnapshotError('Snapshot download exceeds the configured size limit.')
                digest.update(chunk);output.write(chunk)
                if progress and size-reported>=32*1024**2:
                    progress(f'Downloading archive: {size/1024**2:,.0f} MiB received')
                    reported=size
    if digest.hexdigest()!=expected_sha256.lower():raise SnapshotError('Snapshot SHA-256 does not match. Check the release asset and configured digest.')


def _find_layout(root,settings):
    if settings.get('model_subdir'):
        model=inside(root,settings['model_subdir'])
    else:
        candidates=[p for p in root.rglob('model') if p.is_dir() and any((p/m).is_dir() for m in MODELS)]
        if len(candidates)!=1:raise SnapshotError('Cannot identify one model directory. Configure cloud.model_subdir relative to the ZIP root.')
        model=candidates[0]
    if not model.is_dir():raise SnapshotError('The configured model directory is missing.')
    if settings.get('metadata_file'):
        metadata=inside(root,settings['metadata_file'])
    else:
        choices=list(root.rglob('ak_station_metadata.parquet'))
        if not choices:
            choices=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ['.parquet','.csv'] and p.parent.name=='metadata']
        if len(choices)!=1:raise SnapshotError('Cannot identify one station metadata file. Configure cloud.metadata_file relative to the ZIP root.')
        metadata=choices[0]
    if not metadata.is_file():raise SnapshotError('The configured station metadata file is missing.')
    refs=inside(root,settings['refs_subdir']) if settings.get('refs_subdir') else model.parent/'derived'/'refs'
    return model,metadata,refs


def _utc(value):
    return pd.to_datetime(value,utc=True).tz_convert(None)


def inspect_snapshot(root,settings,progress=None):
    """Find useful real dates/runs using bounded column queries, not full frames."""
    model_root,metadata,refs_root=_find_layout(root,settings)
    meta=pd.read_parquet(metadata) if metadata.suffix.lower()=='.parquet' else pd.read_csv(metadata)
    station_col='station_id' if 'station_id' in meta else 'stid'
    if station_col not in meta:raise SnapshotError('Station metadata needs station_id or stid.')
    stations=meta[station_col].dropna().astype(str).str.strip().drop_duplicates().tolist()
    if not stations:raise SnapshotError('The snapshot station metadata is empty.')
    def files(model,element):
        source='wind' if element=='gust' else element
        folder=refs_root/source if model=='refs' else model_root/model/element
        found=sorted(folder.glob('*.parquet'))
        if not found and element=='gust':found=sorted((model_root/model/'wind').glob('*.parquet'))
        return list(map(str,found))
    catalog={m:[e for e in get_available_elements(m) if files(m,e)] for m in MODELS if m!='urma'}
    catalog={m:elements for m,elements in catalog.items() if elements}
    selected=None
    with duckdb.connect() as con:
        con.execute("SET TimeZone='UTC'");con.execute("SET memory_limit='256MB'");con.execute('SET threads=2')
        coverage={}
        for element in ['wind','gust','rh','precip6hr','precip24hr','maxt','mint']:
            obsfiles=files('obs',element)
            if not obsfiles:continue
            if progress:progress(f'Checking {element} observation coverage…')
            con.from_parquet(obsfiles,union_by_name=True).create_view('snapshot_obs',replace=True)
            obs_schema=con.sql('SELECT * FROM snapshot_obs LIMIT 0').df()
            time=get_obs_filter_time_column(element)
            if time not in obs_schema:continue
            value=get_obs_value_column(obs_schema,element)
            oid='stid' if 'stid' in obs_schema else 'station_id'
            obsrange=con.execute(f'SELECT min("{time}"),max("{time}") FROM snapshot_obs WHERE isfinite(TRY_CAST("{value}" AS DOUBLE))').fetchone()
            if obsrange[0] is None:continue
            for model in ['nbmqmd','nbm','ndfd','rrfs','refs','hrrr','nbmqmd_exp','nbm_exp']:
                if element not in catalog.get(model,[]):continue
                if progress:progress(f'Checking {model.upper()} {element} forecast coverage…')
                register_forecast_archive(con,files(model,element),model,element)
                schema=con.sql('SELECT * FROM forecast_archive LIMIT 0').df()
                point=get_model_value_column(schema,model,element,'50')
                target=forecast_target_sql(model,element)
                limits=con.execute(f'SELECT min({target}),max({target}) FROM forecast_archive WHERE isfinite(TRY_CAST("{point}" AS DOUBLE))').fetchone()
                if limits[0] is None:continue
                lo=max(_utc(limits[0]),_utc(obsrange[0]));hi=min(_utc(limits[1]),_utc(obsrange[1]))
                if lo>hi:continue
                coverage[model]=(lo,hi)
                if selected is None:
                    end=_utc(settings['end_date']) if settings.get('end_date') else hi.normalize()
                    start=_utc(settings['start_date']) if settings.get('start_date') else max(lo.normalize(),end-pd.Timedelta(days=6))
                    if start>end or start.date()<lo.date() or end.date()>hi.date():
                        raise SnapshotError('Configured demo dates are outside the default model/observation coverage.')
                    # Sample real station IDs with both model and observation data.
                    ids=con.execute(f'''SELECT DISTINCT station_id FROM forecast_archive
                        WHERE station_id IN (SELECT unnest(?)) AND ({target}) BETWEEN ? AND ?
                        AND isfinite(TRY_CAST("{point}" AS DOUBLE))
                        INTERSECT SELECT DISTINCT "{oid}" FROM snapshot_obs
                        WHERE "{time}" BETWEEN ? AND ? AND isfinite(TRY_CAST("{value}" AS DOUBLE)) LIMIT 5''',
                        [stations,start,end+pd.Timedelta(days=1),start,end+pd.Timedelta(days=1)]).fetchall()
                    if not ids:continue
                    init_expr=('valid_time-forecast_hour*INTERVAL \'1 hour\'' if model=='ndfd' else 'init_time')
                    run=con.execute(f'''SELECT max({init_expr}) FROM forecast_archive
                        WHERE ({target}) BETWEEN ? AND ? AND {init_expr} <= ?
                        AND isfinite(TRY_CAST("{point}" AS DOUBLE))''',[start,end+pd.Timedelta(days=1),start]).fetchone()[0]
                    if run is None:
                        run=con.execute(f'SELECT min({init_expr}) FROM forecast_archive WHERE ({target}) BETWEEN ? AND ?',
                            [start,end+pd.Timedelta(days=1)]).fetchone()[0]
                    selected=dict(model=model,element=element,start_date=str(start.date()),end_date=str(end.date()),
                        init_time=str(_utc(run)),stations=[str(row[0]) for row in ids],
                        coverage_start=str(lo.date()),coverage_end=str(hi.date()))
            if selected:break
    if selected is None:raise SnapshotError('No supported model/observation cases overlap in this snapshot.')
    other=next((m for m in ['ndfd','nbm','nbmqmd','rrfs','refs','hrrr'] if m!=selected['model'] and m in coverage
                and max(coverage[m][0].date(),pd.Timestamp(selected['start_date']).date())<=
                    min(coverage[m][1].date(),pd.Timestamp(selected['end_date']).date())),selected['model'])
    selected.update(comparison_model=other,model_root=str(model_root),metadata_path=str(metadata),
        refs_root=str(refs_root),catalog=catalog)
    return selected


def prepare_snapshot(settings,token=None,session=None,progress=None):
    digest=str(settings.get('archive_sha256','')).lower()
    if not re.fullmatch('[0-9a-f]{64}',digest):raise SnapshotError('Set cloud.archive_sha256 to the release asset SHA-256.')
    url=str(settings.get('archive_url',''))
    if not url:raise SnapshotError('Set cloud.archive_url to the versioned ZIP asset download URL.')
    base=Path(settings.get('cache_dir',Path(tempfile.gettempdir())/'verification-app-cloud')).expanduser().resolve()
    base.mkdir(parents=True,exist_ok=True)
    fingerprint=hashlib.sha256((url+'\n'+digest).encode()).hexdigest()[:24]
    destination=base/fingerprint
    with FileLock(str(base/(fingerprint+'.lock')),timeout=1800):
        marker=destination/'snapshot-ready.json'
        if marker.is_file():
            saved=json.loads(marker.read_text())
            if (saved.get('archive_sha256')==digest and (destination/saved['model_relative']).is_dir()
                    and (destination/saved.get('metadata_relative','missing')).is_file()):
                if progress:progress('Checking cached archive coverage and default dates…')
                return inspect_snapshot(destination,settings,progress=progress)
        with tempfile.TemporaryDirectory(prefix='snapshot-',dir=base) as temporary:
            temporary=Path(temporary);archive=temporary/'archive.zip';payload=temporary/'payload';payload.mkdir()
            download_snapshot(url,archive,digest,token,session,progress=progress)
            extract_snapshot(archive,payload,int(settings.get('max_extracted_bytes',20*1024**3)),progress=progress)
            if progress:progress('Checking archive coverage and selecting default dates…')
            preview=inspect_snapshot(payload,settings,progress=progress)
            manifest={'archive_sha256':digest,'model_relative':str(Path(preview['model_root']).relative_to(payload)),
                      'metadata_relative':str(Path(preview['metadata_path']).relative_to(payload)),
                      'snapshot_id':str(settings.get('snapshot_id',fingerprint))}
            (payload/'snapshot-ready.json').write_text(json.dumps(manifest))
            if destination.exists():shutil.rmtree(destination)
            os.replace(payload,destination)
        # Coverage is already validated; only the three absolute paths moved.
        for key in ['model_root','metadata_path','refs_root']:
            preview[key]=str(destination/Path(preview[key]).relative_to(payload))
        return preview

