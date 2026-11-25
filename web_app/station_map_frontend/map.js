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
let selectable = true;
let screenshotName = 'station-map';
const screenshotButton = document.getElementById('save-screenshot');

async function saveScreenshot() {
  const status = document.getElementById('screenshot-status');
  screenshotButton.disabled = true;
  status.textContent = '';
  try {
    const basemap = mapInstance?.getMapboxMap();
    const overlay = mapInstance?.getCanvas();
    if (!basemap?.isStyleLoaded() || !overlay?.width) {
      throw new Error('Wait for the map to load, then try again.');
    }

    // Redraw both layers at the current camera before compositing their buffers.
    basemap.redraw();
    mapInstance.redraw('screenshot');
    const image = document.createElement('canvas');
    image.width = overlay.width;
    image.height = overlay.height;
    const context = image.getContext('2d');
    context.fillStyle = 'white';
    context.fillRect(0, 0, image.width, image.height);
    context.drawImage(basemap.getCanvas(), 0, 0, image.width, image.height);
    context.drawImage(overlay, 0, 0, image.width, image.height);

    const attribution = document.querySelector('.maplibregl-ctrl-attrib-inner')?.textContent.trim()
      || '© OpenStreetMap contributors © CARTO';
    const scale = image.width / overlay.getBoundingClientRect().width;
    context.font = `${12 * scale}px sans-serif`;
    const textWidth = context.measureText(attribution).width;
    context.fillStyle = '#fffffff0';
    context.fillRect(image.width - textWidth - 12 * scale, image.height - 20 * scale,
      textWidth + 12 * scale, 20 * scale);
    context.fillStyle = '#222';
    context.fillText(attribution, image.width - textWidth - 6 * scale, image.height - 6 * scale);

    const png = await new Promise(resolve => image.toBlob(resolve, 'image/png'));
    if (!png) throw new Error('The browser could not save the map image.');
    const url = URL.createObjectURL(png);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${screenshotName}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    status.textContent = error.message;
  } finally {
    screenshotButton.disabled = false;
  }
}

screenshotButton.addEventListener('click', saveScreenshot);

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
  }), ...(records.some(d => d.event_symbol) ? [new deck.TextLayer({
    id: 'probability-event-symbols',
    data: records.filter(d => d.event_symbol),
    getPosition: d => [d.longitude, d.latitude],
    getText: d => d.event_symbol,
    getSize: 12, sizeUnits: 'pixels',
    getColor: [255,255,255,255],
    characterSet: '+!', fontSettings: {sdf: true},
    fontWeight: 'bold', outlineWidth: 0.12, outlineColor: [20,20,20,255],
    getTextAnchor: 'middle', getAlignmentBaseline: 'center',
    // The visible symbol must pick its own station, even above colocated sites.
    pickable: true
  })] : [])];
}

function toggleStation(info) {
  if (!selectable || !info.object) return;
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
  if (object.tooltip_lines) {
    return {text: object.tooltip_lines.join('\n'), style: {backgroundColor: 'white', color: 'black'}};
  }
  const lines = [object.station_id, `${metric}: ${object.metric_value_text ?? object.metric_value ?? '—'}`];
  const times = object.forecast_date ? ['forecast_date', 'valid_time', 'obs_window_start', 'obs_window_end']
    : object.model_window_start ? ['model_window_start', 'model_window_end', 'obs_window_start', 'obs_window_end', 'obs_time_offset_minutes']
    : ['forecast_hour', 'obs_valid_time', 'obs_time_offset_minutes'];
  for (const field of ['model_value', 'median_value', 'obs_value', 'rank_label', 'interval_bounds', 'n_available', 'n_expected', 'complete', 'probability_source', 'probability_text', 'probability_outcome', ...times, 'mnet_id', 'elevation_ft', 'wfo_best', 'wfo_assignment_source']) {
    if (object[field] != null) lines.push(`${field}: ${object[field]}`);
  }
  for (const field of ['n', 'bias', 'mae', 'rmse', 'pod', 'far', 'csi', 'n_prob', 'mean_probability_pct', 'prob_observed_frequency_pct', 'probability_bias_pp', 'prob_observed_events', 'n_zero_probability', 'zero_probability_events', 'zero_probability_event_rate_pct']) {
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
  selectable = args.selectable !== false;
  screenshotName = [args.screenshot_name || 'station-map', metric].join('-')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const mapLabel = selectable ? 'Station metric map. Click a station to toggle selection.' : 'Station comparison map.';
  document.getElementById('map').setAttribute('aria-label', mapLabel);
  try {
    if (!window.deck || !window.maplibregl) throw new Error('Map libraries could not load. Check access to unpkg.com and reload the page.');
    if (!mapInstance) {
      viewState = args.initial_view;
      mapInstance = new deck.DeckGL({
        container: 'map', map: maplibregl,
        mapStyle: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
        mapOptions: {preserveDrawingBuffer: true},
        viewState, controller: {scrollZoom: scrollZoomEnabled}, layers: layers(),
        onViewStateChange: ({viewState: next}) => {
          viewState = next;
          mapInstance.setProps({viewState});
        },
        onLoad: () => { screenshotButton.disabled = false; },
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

