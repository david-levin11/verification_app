"""Shared map selection, explicitly copied into each verification page."""
import hashlib
import streamlit as st
from page_controls import PageControls, set_page_value

SELECTION_KEY = 'selected_station_list'


def parse_station_ids(text):
    return list(dict.fromkeys(s.strip().upper() for s in text.replace('\n', ',').split(',') if s.strip()))


def selected_station_ids():
    return list(st.session_state.get(SELECTION_KEY, []))


def update_map_selection(chart_key, layer_id):
    event = st.session_state.get(chart_key, {})
    objects = event.get('selection', {}).get('objects', {}).get(layer_id, [])
    current = {str(obj['station_id']) for obj in objects if 'station_id' in obj}
    previous_key = f'_previous_{chart_key}'
    previous = set(st.session_state.get(previous_key, []))
    selected = set(selected_station_ids())
    # Each native multi-object click toggles one station. Apply the delta to
    # shared selection so filters and a second map cannot erase hidden sites.
    selected.symmetric_difference_update(previous.symmetric_difference(current))
    st.session_state[SELECTION_KEY] = sorted(selected)
    st.session_state[previous_key] = sorted(current)


def selectable_chart(deck, layer_id, station_ids, name):
    ids = '|'.join(map(str, station_ids))
    digest = hashlib.sha256(ids.encode()).hexdigest()[:12]
    epoch = st.session_state.get('_station_selection_epoch', 0)
    key = f'station_picker_{name}_{digest}_{epoch}'
    if key not in st.session_state:
        st.session_state[f'_previous_{key}'] = []
    st.pydeck_chart(deck, key=key, selection_mode='multi-object',
        on_select=lambda: update_map_selection(key, layer_id))


def remove_station(station_id=None):
    st.session_state[SELECTION_KEY] = ([s for s in selected_station_ids() if s != station_id]
                                       if station_id else [])
    # Native chart selection is read-only; remount only for explicit removal.
    st.session_state['_station_selection_epoch'] = st.session_state.get('_station_selection_epoch', 0) + 1


def show_selected_stations(metadata):
    selected = selected_station_ids()
    st.subheader(f'Selected map stations ({len(selected)})')
    st.caption('Selection persists across filters and pages. Import it with “Use selected map stations” on Aggregate Verification or Model Comparison.')
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


def import_map_stations(page, key):
    set_page_value(page, key, ', '.join(selected_station_ids()))
    if page == 'compare':
        set_page_value(page, 'compare_filtered_stations', False)


def station_ids_input(page, key, label, default='PAJN'):
    count = len(selected_station_ids())
    st.button('Use selected map stations', key=f'{page}_import_map', disabled=count == 0,
        on_click=import_map_stations, args=(page, key),
        help='Replace this page’s station IDs with the current map selection.')
    st.caption(f'{count} stations in the shared map selection. You can also type station IDs below.')
    return PageControls(page).text_input(label, default, key=key)
