"""Browser regression: python tests/browser_station_map.py

Optional development dependencies: playwright and its Chromium browser.
Uses synthetic metrics, without reading or changing forecast archives.
"""
from pathlib import Path
import socket
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).parents[1] / 'web_app'


def main():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as folder:
        app = Path(folder) / 'map_app.py'
        app.write_text(f'''
import sys
sys.path.insert(0, {str(ROOT)!r})
import pandas as pd
import streamlit as st
from maps import plot_station_metric_map
from station_selection import show_selected_stations, station_ids_input
st.set_page_config(layout='wide')
data = pd.DataFrame({{'station_id':['PAJN','PANC'], 'latitude':[58.30,58.30],
    'longitude':[-134.50,-134.00], 'mae':[1.,2.], 'n':[20,30]}})
plot_station_metric_map(data, 'mae')
show_selected_stations(data)
station_ids_input('aggregate', 'aggregate_station_ids_input', 'Aggregate station IDs', default='')
station_ids_input('compare', 'compare_stations', 'Comparison station IDs', default='')
''')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        log = (Path(folder) / 'server.log').open('w+')
        server = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(app),
            '--server.headless=true', '--server.address=127.0.0.1', f'--server.port={port}', '--browser.gatherUsageStats=false'],
            stdout=log, stderr=subprocess.STDOUT)
        try:
            url = f'http://127.0.0.1:{port}'
            for _ in range(150):
                try:
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url + '/_stcore/health', timeout=1)
                    break
                except OSError as exc:
                    last_error = exc
                    time.sleep(.2)
            else:
                raise RuntimeError(f'Streamlit did not start: {last_error}')
            print('Browser server ready', flush=True)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox',
                    '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
                page = browser.new_page(viewport={'width':1280,'height':1100}, ignore_https_errors=True)
                # Optional local copies of the pinned CDN assets for restricted CI.
                assets = os.environ.get('STATION_MAP_TEST_ASSETS')
                if assets:
                    def asset(route):
                        name = ('station_map_deck.js' if '/deck.gl@' in route.request.url else
                                'station_map_maplibre.css' if route.request.url.endswith('.css') else
                                'station_map_maplibre.js')
                        route.fulfill(path=str(Path(assets) / name))
                    page.route('https://unpkg.com/**', asset)
                page.on('pageerror', lambda error: print('Browser error:', error, flush=True))
                page.goto(url)
                page.wait_for_selector('iframe')
                frame = next(f for f in page.frames if '/component/' in f.url)
                try:
                    frame.wait_for_function('typeof mapInstance !== "undefined" && mapInstance && mapInstance.getViewports().length > 0', timeout=30000)
                except Exception:
                    print('Map status:', frame.locator('body').inner_text(), flush=True)
                    raise
                assert not frame.locator('#error').is_visible()
                bounds = frame.frame_element().bounding_box()
                page.mouse.move(bounds['x']+bounds['width']/2, bounds['y']+250)
                page.mouse.wheel(0, -500)
                frame.wait_for_function('viewState.zoom > 4.5')
                page.wait_for_timeout(500)  # allow wheel inertia to settle
                def view():
                    return frame.evaluate('Object.fromEntries(["latitude","longitude","zoom","pitch","bearing"].map(k=>[k,viewState[k]]))')
                zoomed = view()
                def unchanged():
                    actual = view()
                    for key in zoomed:
                        assert abs(actual[key]-zoomed[key]) < 1e-7, (key, zoomed, actual)
                def click_station(station_id):
                    xy = frame.evaluate('(id) => {const d=records.find(d=>d.station_id===id); return mapInstance.getViewports()[0].project([d.longitude,d.latitude]);}', station_id)
                    box = frame.frame_element().bounding_box()
                    picked = frame.evaluate('(xy) => mapInstance.pickObject({x:xy[0],y:xy[1],radius:3})?.object?.station_id', xy)
                    assert picked == station_id, 'The fixture stations must be individually pickable'
                    page.mouse.click(box['x']+xy[0], box['y']+xy[1])
                def ids(expected):
                    from playwright.sync_api import expect
                    expect(page.get_by_label('Aggregate station IDs', exact=True)).to_have_value(expected)
                    expect(page.get_by_label('Comparison station IDs', exact=True)).to_have_value(expected)
                    unchanged()
                click_station('PAJN'); ids('PAJN')
                frame.wait_for_function('selected.has("PAJN")')
                click_station('PAJN'); ids('')
                click_station('PANC'); ids('PANC')
                page.get_by_label('Aggregate station IDs', exact=True).fill('CUSTOM')
                page.get_by_label('Aggregate station IDs', exact=True).press('Enter')
                page.wait_for_timeout(300)
                assert page.get_by_label('Aggregate station IDs', exact=True).input_value() == 'CUSTOM'
                unchanged()
                click_station('PAJN'); ids('PAJN, PANC')
                page.get_by_role('button', name='Remove', exact=True).first.click(); ids('PANC')
                page.get_by_role('button', name='Clear selected stations', exact=True).click(); ids('')
                click_station('PAJN'); click_station('PANC'); ids('PAJN, PANC')
                frame.wait_for_function('[...selected].sort().join(", ") === "PAJN, PANC"')
                assert not page.get_by_text('Use selected map stations', exact=True).count()
                assert not page.get_by_test_id('stException').count()
                browser.close()
                print('Browser checks passed: zoom, toggle, highlight, automatic station fields, manual override, remove, clear.')
        except Exception:
            log.flush(); log.seek(0); print(log.read())
            raise
        finally:
            server.terminate()
            server.wait(timeout=10)
            log.close()


if __name__ == '__main__':
    main()
