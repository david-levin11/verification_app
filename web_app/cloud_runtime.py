"""Opt-in Community Cloud startup. Disabled deployments keep local defaults."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from cloud_snapshot import prepare_snapshot, SnapshotError


def cloud_settings():
    try:return dict(st.secrets.get('cloud',{}))
    except (FileNotFoundError,KeyError):return {}


@st.cache_resource(show_spinner=False)
def _prepare_cached(settings_json,_token=None):
    return prepare_snapshot(json.loads(settings_json),token=_token)


def cloud_context():
    settings=cloud_settings()
    if settings.get('enabled') is not True:return None
    token=settings.pop('github_token',None)
    identity=json.dumps(settings,sort_keys=True,default=str)
    saved=st.session_state.get('_cloud_snapshot_context')
    if saved and saved['identity']==identity and Path(saved['context']['metadata_path']).is_file():
        return saved['context']
    try:
        with st.spinner('Preparing the versioned test archive. The first startup downloads and extracts the data; later visits reuse it.'):
            context=dict(_prepare_cached(identity,_token=token))
            # A cached in-process value must not hide an evicted disk snapshot.
            if not Path(context['metadata_path']).is_file():
                _prepare_cached.clear()
                context=dict(_prepare_cached(identity,_token=token))
    except SnapshotError as exc:
        st.error(f'Test archive setup: {exc}');st.stop()
    except Exception:
        st.error('The test archive could not be downloaded or opened. Check the versioned asset URL, access credentials, ZIP contents and available disk space.');st.stop()
    context['snapshot_id']=str(settings.get('snapshot_id',settings.get('archive_sha256','')[:12]))
    st.session_state['_cloud_snapshot_context']={'identity':identity,'context':context}
    return context


def cloud_widget_defaults(page):
    context=cloud_context()
    if context is None:return {}
    start=pd.Timestamp(context['start_date']).date();end=pd.Timestamp(context['end_date']).date()
    init=pd.Timestamp(context['init_time'])
    station_text=', '.join(context['stations'])
    model=context['model'];element=context['element']
    if page in ['map','aggregate']:
        result={f'{page}_ui_archive_root':context['model_root'],f'{page}_refs_root':context['refs_root'],
            f'{page}_ui_model':model,f'{page}_ui_element':element,
            f'{page}_ui_start_date':start,f'{page}_ui_end_date':end}
        result.update({'map_metadata_path':context['metadata_path']} if page=='map' else
                      {'aggregate_station_ids_input':station_text})
        return result
    if page=='storm':
        return {'storm_Local Archive Root':context['model_root'],'storm_refs_root':context['refs_root'],
            'storm_metadata':context['metadata_path'],'storm_Model':model,'storm_Element':element,
            'storm_init_date':init.date(),'storm_init_hour':init.hour,
            'storm_Plot Start Date':start,'storm_Plot End Date':end}
    if page=='compare':
        return {'compare_archive_root':context['model_root'],'compare_refs_root':context['refs_root'],
            'compare_metadata':context['metadata_path'],'compare_model_a':context['comparison_model'],
            'compare_model_b':model,'compare_element':element,'compare_start':start,'compare_end':end,
            'compare_stations':station_text}
    return {}


def show_cloud_snapshot():
    context=cloud_context()
    if context is None:return
    st.info(f'Test snapshot: {context["snapshot_id"]}. Default {context["element"]} coverage: '
            f'{context["coverage_start"]} through {context["coverage_end"]} UTC. '
            f'The initial selection uses {context["start_date"]} through {context["end_date"]}. '
            'Availability varies by model and element; this is a fixed snapshot, not a live production feed.')
    with st.expander('Models and elements in this snapshot'):
        st.dataframe(pd.DataFrame([{'Model':m.upper(),'Elements':', '.join(e)}
                     for m,e in context['catalog'].items()]),hide_index=True)
