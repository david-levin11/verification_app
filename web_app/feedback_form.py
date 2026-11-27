"""Report bugs or suggestions from a verification page."""

from datetime import date, datetime
import logging
import sqlite3

import streamlit as st

from feedback_queue import (
    CONTACT_LIMIT, DETAILS_LIMIT, FEEDBACK_KINDS, TITLE_LIMIT, feedback_database, save_feedback,
)

# Include only fields that describe a verification run. Exclude archive paths,
# station lists, observations, free-text controls, credentials, and user identity.
_CONTEXT_FIELDS = (
    'model', 'model_a', 'model_b', 'element', 'obs', 'percentile', 'percentile_a',
    'percentile_b', 'start_date', 'end_date', 'start', 'end', 'init',
    'forecast_projection', 'threshold', 'threshold_operator', 'operator',
    'obs_time_tolerance', 'obs_minutes', 'minutes', 'offset', 'offset_hours',
    'ref_tolerance', 'reference_hours', 'align_by_date',
)


def _feedback_context(settings):
    context = {}
    for key in _CONTEXT_FIELDS:
        value = settings.get(key)
        if isinstance(value, (date, datetime)):
            context[key] = value.isoformat()
        elif isinstance(value, (str, int, float, bool)):
            context[key] = value
    return context


def _submit_feedback(page, keys, context):
    try:
        receipt = save_feedback(
            feedback_database(), page=page, kind=st.session_state[keys['kind']],
            title=st.session_state[keys['title']], details=st.session_state[keys['details']],
            contact=st.session_state[keys['contact']],
            context=context if st.session_state.get(keys['include_context']) else None,
        )
    except ValueError as exc:
        st.session_state[keys['notice']] = ('error', str(exc))
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).exception('Unable to save feedback')
        st.session_state[keys['notice']] = ('error', 'Could not save your feedback. Please try again.')
    else:
        st.session_state[keys['notice']] = ('success', f'Feedback saved. Reference ID {receipt}')
        for field in ('title', 'details', 'contact'):
            st.session_state[keys[field]] = ''
        st.session_state[keys['include_context']] = False


def show_feedback(page, settings=None):
    context = _feedback_context(settings or {})
    prefix = f'feedback_{page.lower().replace(" ", "_")}'
    keys = {field: f'{prefix}_{field}' for field in
            ('kind', 'title', 'details', 'contact', 'include_context', 'notice')}
    with st.sidebar.popover('Send feedback'):
        st.caption('Report a bug or suggest an improvement. Feedback goes to the app’s private queue.')
        if notice := st.session_state.pop(keys['notice'], None):
            level, message = notice
            (st.success if level == 'success' else st.error)(message)
        if context:
            with st.expander('Preview optional app settings'):
                st.text('\n'.join(f"{key.replace('_', ' ').capitalize()}: {value}"
                                  for key, value in context.items()))
        with st.form(prefix):
            st.selectbox('Feedback type', FEEDBACK_KINDS, key=keys['kind'])
            st.text_input('Summary', max_chars=TITLE_LIMIT, key=keys['title'])
            st.text_area('What happened or what would you improve?', max_chars=DETAILS_LIMIT, key=keys['details'])
            st.text_input('Contact (optional)', max_chars=CONTACT_LIMIT, key=keys['contact'])
            if context:
                st.checkbox('Include the app settings shown above', key=keys['include_context'])
            st.form_submit_button('Submit feedback', on_click=_submit_feedback, args=(page, keys, context))
