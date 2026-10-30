// The map and its viewport live for the lifetime of this component iframe.
// A Streamlit render updates data/selection, never the user's camera position.
let mapInstance = null;
let viewState = null;
let records = [];
let selected = new Set();
let metric = '';
let sequence = 0;
let latestEventId = null;
const instanceId = `${Date.now()}-${Math.random()}`;
let scrollZoomEnabled = false;

function zoomBy(amount) {
  if (!mapInstance || !viewState) return;
  viewState = {...viewState, zoom: Math.max(0, Math.min(20, viewState.zoom + amount))};
  mapInstance.setProps({viewState});
}
document.getElementById('zoom-in').addEventListener('click', () => zoomBy(1));
document.getElementById('zoom-out').addEventListener('click', () => zoomBy(-1));
document.getElementById('scroll-zoom').addEventListener('change', event => {
  scrollZoomEnabled = event.target.checked;
  if (mapInstance) mapInstance.setProps({controller: {scrollZoom: scrollZoomEnabled}});
  document.getElementById('instructions').textContent = scrollZoomEnabled
    ? 'Scroll to zoom is on. Turn it off to scroll the page over the map.'
    : 'Drag to pan. Use + / − to zoom. Scroll to move down the page.';
});

function send(type, payload = {}) {
  window.parent.postMessage({isStreamlitMessage: true, type, ...payload}, '*');
}

function layers() {
  return [new deck.ScatterplotLayer({
    id: 'metric-stations', data: records,
    getPosition: d => [d.longitude, d.latitude],
    getFillColor: d => d.fill_color,
    getRadius: d => d.point_radius,
    radiusUnits: 'pixels', radiusMinPixels: 3, radiusMaxPixels: 10,
    pickable: true, stroked: true,
    getLineColor: d => selected.has(d.station_id) ? [255, 190, 0, 255] : (d.event_outline_color || [40, 40, 40, 180]),
    getLineWidth: d => selected.has(d.station_id) ? 3 : (d.event_outline_color ? 2 : 1),
    lineWidthUnits: 'pixels',
    updateTriggers: {getLineColor: [...selected].join('|'), getLineWidth: [...selected].join('|')}
  })];
}

function toggleStation(info) {
  if (!info.object) return; // Clicking the background leaves the list alone.
  const id = info.object.station_id;
  if (selected.has(id)) selected.delete(id); else selected.add(id);
  mapInstance.setProps({layers: layers()});
  latestEventId = `${instanceId}-${++sequence}`;
  send('streamlit:setComponentValue', {dataType: 'json', value: {
    event_id: latestEventId,
    clicked_station_id: id,
    station_ids: [...selected].sort(),
    view_state: Object.fromEntries(['latitude', 'longitude', 'zoom', 'pitch', 'bearing'].map(k => [k, viewState[k]]))
  }});
}

function tooltip({object}) {
  if (!object) return null;
  const lines = [object.station_id, `${metric}: ${object.metric_value_text ?? object.metric_value ?? '—'}`];
  const times = object.forecast_date ? ['forecast_date', 'valid_time', 'obs_window_start', 'obs_window_end']
    : object.model_window_start ? ['model_window_start', 'model_window_end', 'obs_window_start', 'obs_window_end', 'obs_time_offset_minutes']
    : ['forecast_hour', 'obs_valid_time', 'obs_time_offset_minutes'];
  for (const field of ['model_value', 'median_value', 'obs_value', 'rank_label', 'interval_bounds', 'n_available', 'n_expected', 'complete', 'probability_source', ...times, 'mnet_id', 'elevation_ft']) {
    if (object[field] != null) lines.push(`${field}: ${object[field]}`);
  }
  for (const field of ['n', 'bias', 'mae', 'rmse', 'pod', 'far', 'csi']) {
    if (field !== metric && object[field] != null) lines.push(`${field.toUpperCase()}: ${object[field]}`);
  }
  return {text: lines.join('\n'), style: {backgroundColor: 'white', color: 'black'}};
}

function render(event) {
  if (event.source !== window.parent || event.data.type !== 'streamlit:render') return;
  const args = event.data.args;
  records = args.records;
  // Ignore stale render acknowledgements while clicks are in flight.
  if (latestEventId === null || args.ack_event_id === latestEventId) {
    selected = new Set(args.selected_ids);
  }
  metric = args.metric;
  try {
    if (!window.deck || !window.maplibregl) throw new Error('Map libraries could not load. Check access to unpkg.com and reload the page.');
    if (!mapInstance) {
      viewState = args.initial_view;
      mapInstance = new deck.DeckGL({
        container: 'map', map: maplibregl,
        mapStyle: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
        viewState, controller: {scrollZoom: scrollZoomEnabled}, layers: layers(),
        onViewStateChange: ({viewState: next}) => {
          viewState = next;
          mapInstance.setProps({viewState});
        },
        onClick: toggleStation, getTooltip: tooltip
      });
    } else {
      // In particular, do not set initialViewState/viewState here.
      mapInstance.setProps({layers: layers(), getTooltip: tooltip});
    }
  } catch (error) {
    const message = document.getElementById('error');
    message.textContent = error.message;
    message.style.display = 'block';
  }
  send('streamlit:setFrameHeight', {height: 520});
}
window.addEventListener('message', render);
send('streamlit:componentReady', {apiVersion: 1});
send('streamlit:setFrameHeight', {height: 520});

