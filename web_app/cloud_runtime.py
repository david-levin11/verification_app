"""Opt-in Community Cloud startup. Disabled deployments keep local defaults."""
import json
import logging
from concurrent.futures import Future
from threading import Lock, Thread
from pathlib import Path
import pandas as pd
import streamlit as st
from cloud_snapshot import prepare_snapshot, SnapshotError

_LOGGER=logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)
if not _LOGGER.handlers:
    _LOGGER.addHandler(logging.StreamHandler())
_LOGGER.propagate=False


def cloud_settings():
    try:return dict(st.secrets.get('cloud',{}))
    except (FileNotFoundError,KeyError):return {}


class SnapshotJob:
    """One shared worker; it never calls Streamlit from its background thread."""
    def __init__(self,settings_json,token=None):
        self.future=Future()
        self._lock=Lock()
        self._status='Starting archive preparation…'
        def run():
            try:
                context=prepare_snapshot(json.loads(settings_json),token=token,progress=self.update)
            except Exception as exc:
                _LOGGER.exception('Cloud snapshot preparation failed')
                self.future.set_exception(exc)
            else:
                self.update('Archive ready.')
                self.future.set_result(context)
        Thread(target=run,name='cloud-snapshot',daemon=True).start()

    def update(self,message):
        with self._lock:self._status=message
        _LOGGER.info('Cloud snapshot: %s',message)

    def status(self):
        with self._lock:return self._status


@st.cache_resource(show_spinner=False)
def _snapshot_job(settings_json,_token=None):
    return SnapshotJob(settings_json,_token)


@st.fragment(run_every='2s')
def _preparation_status(job):
    if job.future.done():
        st.rerun()
    st.info('Preparing the test archive. This can take several minutes on the first startup.')
    st.write(job.status())
    st.caption('This page updates automatically when the archive is ready.')
    if st.button('Check archive status',key='cloud_check_status'):st.rerun()


def cloud_context():
    settings=cloud_settings()
    if settings.get('enabled') is not True:return None
    token=settings.pop('github_token',None)
    identity=json.dumps(settings,sort_keys=True,default=str)
    saved=st.session_state.get('_cloud_snapshot_context')
    if saved and saved['identity']==identity and Path(saved['context']['metadata_path']).is_file():
        return saved['context']
    # Deployment health checks execute the script too. Only a browser button
    # starts preparation, after Streamlit has delivered the landing screen.
    if st.session_state.get('_cloud_prepare_requested')!=identity:
        st.title('Alaska Point Verification Dashboard')
        st.info('The dashboard is ready to connect to the test archive.')
        st.caption('Prepare the archive to open verification pages. The first preparation downloads the snapshot; later sessions reuse it.')
        if st.button('Prepare test archive',key='cloud_prepare'):
            st.session_state['_cloud_prepare_requested']=identity
            st.rerun()
        st.stop()
    job=_snapshot_job(identity,_token=token)
    if job.future.done() and not job.future.exception():
        if not Path(job.future.result()['metadata_path']).is_file():
            _snapshot_job.clear()
            job=_snapshot_job(identity,_token=token)
    if not job.future.done():
        _preparation_status(job)
        st.stop()
    try:
        context=dict(job.future.result())
    except Exception as exc:
        if isinstance(exc,SnapshotError):st.error(f'Test archive setup: {exc}')
        else:st.error('The test archive could not be downloaded or opened. Check the deployment logs for details, the asset URL, ZIP contents and available disk space.')
        if st.button('Retry archive preparation',key='cloud_retry'):
            _snapshot_job.clear()
            st.rerun()
        st.stop()
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
