"""Station metric map with a browser-owned viewport across Streamlit reruns."""
from pathlib import Path
import json
import streamlit as st
import streamlit.components.v1 as components
from station_selection import selected_station_ids, set_map_station_ids

_station_map = components.declare_component(
    'station_metric_map', path=str(Path(__file__).with_name('station_map_frontend')))


def apply_map_event(event):
    if not isinstance(event, dict) or not event.get('event_id'):
        return
    if event['event_id'] == st.session_state.get('_station_map_last_event'):
        return
    st.session_state['_station_map_last_event'] = event['event_id']
    set_map_station_ids(event.get('station_ids', []))
    view = event.get('view_state', {})
    fields = ['latitude', 'longitude', 'zoom', 'pitch', 'bearing']
    if all(isinstance(view.get(k), (int, float)) for k in fields):
        st.session_state['_station_map_view'] = {k: view[k] for k in fields}
    return True


def station_metric_map(data, selected_metric):
    apply_map_event(st.session_state.get('station_metric_map'))
    # Dataframe JSON conversion replaces NaN with null and handles numpy types.
    records = json.loads(data.to_json(orient='records'))
    view = st.session_state.get('_station_map_view', dict(
        latitude=float(data.latitude.mean()), longitude=float(data.longitude.mean()),
        zoom=4, pitch=0, bearing=0))
    event = _station_map(records=records, metric=selected_metric,
        selected_ids=selected_station_ids(), initial_view=view,
        ack_event_id=st.session_state.get('_station_map_last_event'), screenshot_name='verification-overview',
        default=None, key='station_metric_map')
    if apply_map_event(event):
        st.rerun()


def comparison_station_map(data, view, metric, label_a, label_b, key):
    """Render comparison markers in a map with an independent camera."""
    fields = ['station_id', 'latitude', 'map_longitude', 'color', 'point_radius',
              'a', 'b', 'n', 'advantage', 'mnet_id', 'elevation_ft']
    records = json.loads(data[[field for field in fields if field in data]]
                         .rename(columns={'map_longitude': 'longitude', 'color': 'fill_color'})
                         .to_json(orient='records'))
    for record in records:
        lines = [record['station_id']]
        if record.get('mnet_id') is not None:
            lines.append(f"Network ID: {record['mnet_id']}")
        if record.get('elevation_ft') is not None:
            lines.append(f"Elevation: {record['elevation_ft']} ft")
        for label, field in [(label_a, 'a'), (label_b, 'b'), ('Advantage for A', 'advantage')]:
            lines.append(f"{label}: {record[field]:.3g}" if record[field] is not None else f"{label}: —")
        lines.append(f"Cases: {record['n']:,}")
        record['tooltip_lines'] = lines
    camera_key = f'{key}_{view.latitude:.5f}_{view.longitude:.5f}_{view.zoom:.3f}'
    _station_map(records=records, metric=metric, selected_ids=[],
                 initial_view=dict(latitude=view.latitude, longitude=view.longitude,
                                   zoom=view.zoom, pitch=0, bearing=0),
                 selectable=False, screenshot_name=key, key=camera_key, default=None)
