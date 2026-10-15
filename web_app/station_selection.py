"""Map selections propagate automatically; manual entries last until the next map change."""
import streamlit as st
from page_controls import PageControls, set_page_value

SELECTION_KEY = 'selected_station_list'


def parse_station_ids(text):
    return list(dict.fromkeys(s.strip().upper() for s in text.replace('\n', ',').split(',') if s.strip()))


def selected_station_ids():
    return list(st.session_state.get(SELECTION_KEY, []))


def set_map_station_ids(ids):
    selected = sorted(set(str(s).strip().upper() for s in ids if str(s).strip()))
    if SELECTION_KEY not in st.session_state or selected != selected_station_ids():
        st.session_state[SELECTION_KEY] = selected
        st.session_state['_map_selection_revision'] = st.session_state.get('_map_selection_revision', 0) + 1


def remove_station(station_id=None):
    set_map_station_ids([s for s in selected_station_ids() if s != station_id] if station_id else [])


def show_selected_stations(metadata):
    selected = selected_station_ids()
    st.subheader(f'Selected map stations ({len(selected)})')
    st.caption('Changes carry over automatically to Aggregate Verification and Model Comparison. You can also enter station IDs manually on those pages.')
    if not selected:
        st.info('Click stations on the map to select them; click again to remove them.')
        return
    names = {}
    if 'station_id' in metadata:
        name_col = next((c for c in ['station_name', 'name'] if c in metadata), None)
        if name_col:
            names = metadata.drop_duplicates('station_id').set_index('station_id')[name_col].fillna('').to_dict()
    for station_id in selected:
        text, button = st.columns([5, 1])
        text.write(f'{station_id} — {names[station_id]}' if names.get(station_id) else station_id)
        button.button('Remove', key=f'remove_map_{station_id}', on_click=remove_station, args=(station_id,))
    st.button('Clear selected stations', key='clear_map_stations', on_click=remove_station)


def sync_map_selection(page, key):
    """Apply each map change once, leaving later manual edits alone."""
    revision = st.session_state.get('_map_selection_revision', 0)
    seen_key = f'_map_selection_seen_{page}'
    if SELECTION_KEY in st.session_state and st.session_state.get(seen_key) != revision:
        set_page_value(page, key, ', '.join(selected_station_ids()))
        if page == 'compare':
            set_page_value(page, 'compare_filtered_stations', False)
        st.session_state[seen_key] = revision


def station_ids_input(page, key, label, default='PAJN'):
    sync_map_selection(page, key)
    st.caption('Map selections carry over automatically. You can edit the station IDs below; a new map selection replaces them.')
    saved = st.session_state.get(f'_page_settings_{page}', {})
    if key in st.session_state or key in saved:
        return PageControls(page).text_input(label, key=key)
    return PageControls(page).text_input(label, default, key=key)
