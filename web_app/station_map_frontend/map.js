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
    getLineColor: d => selected.has(d.station_id) ? [255, 190, 0, 255] : [40, 40, 40, 180],
    getLineWidth: d => selected.has(d.station_id) ? 3 : 1,
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
    station_ids: [...selected].sort(),
    view_state: Object.fromEntries(['latitude', 'longitude', 'zoom', 'pitch', 'bearing'].map(k => [k, viewState[k]]))
  }});
}

function tooltip({object}) {
  if (!object) return null;
  const lines = [object.station_id, `${metric}: ${object.metric_value ?? '—'}`];
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
        viewState, controller: true, layers: layers(),
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
