"""Optional real-browser storm map regression: python tests/browser_storm_page.py."""
from pathlib import Path
from datetime import date
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import pandas as pd

ROOT=Path(__file__).parents[1]/'web_app'


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--element',choices=['wind','maxt','mint'],default='wind')
    element=parser.parse_args().element
    from playwright.sync_api import sync_playwright, expect
    from test_storm_analysis import frames, metadata
    from test_temperature_storm import temperature_frames
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder)
        daily=element in ['maxt','mint']
        m,o=temperature_frames(element) if daily else frames()
        for model,frame in [('nbmqmd',m),('obs',o)]:
            path=base/model/element;path.mkdir(parents=True)
            month_values=frame.date if daily and model=='obs' else frame.init_time if model!='obs' else frame.valid_time
            for month,part in frame.groupby(month_values.dt.strftime('%Y_%m')):
                part.to_parquet(path/f'{month}_archive.parquet',index=False)
        metadata().to_parquet(base/'stations.parquet',index=False)
        app=base/'storm_app.py'
        defaults={'storm_Local Archive Root':str(base),'storm_Model':'nbmqmd','storm_Element':element,
            'storm_metadata':str(base/'stations.parquet'),
            'storm_Model Init Time (YYYY-MM-DD HH:MM:SS)':str(m.init_time.iloc[0]),
            'storm_Plot Start Date':m.valid_time.min().date(),'storm_Plot End Date':m.valid_time.max().date(),
            'storm_station_scope':'Map Explorer selections','selected_station_list':['A','B']}
        app.write_text(f'''
import sys, runpy, datetime
sys.path.insert(0,{str(ROOT)!r})
import streamlit as st
st.set_page_config(layout='wide')
for key,value in {defaults!r}.items():
    if key not in st.session_state:st.session_state[key]=value
runpy.run_path({str(ROOT/'pages/3_Storm_Zoom.py')!r})
''')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        log=(base/'server.log').open('w+')
        server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(app),
            '--server.headless=true','--server.address=127.0.0.1',f'--server.port={port}',
            '--browser.gatherUsageStats=false'],stdout=log,stderr=subprocess.STDOUT)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(150):
                try:
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url+'/_stcore/health',timeout=1)
                    break
                except OSError:time.sleep(.2)
            else:raise RuntimeError('Streamlit did not start')
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,args=['--no-sandbox','--use-gl=angle',
                    '--use-angle=swiftshader','--enable-unsafe-swiftshader'])
                page=browser.new_page(viewport={'width':1400,'height':1000},ignore_https_errors=True)
                assets=os.environ.get('STATION_MAP_TEST_ASSETS')
                if assets:
                    def asset(route):
                        name=('station_map_deck.js' if '/deck.gl@' in route.request.url else
                              'station_map_maplibre.css' if route.request.url.endswith('.css') else 'station_map_maplibre.js')
                        route.fulfill(path=str(Path(assets)/name))
                    page.route('https://unpkg.com/**',asset)
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(url)
                page.get_by_role('button',name='Generate Storm Timeseries',exact=True).click()
                page.wait_for_selector('iframe')
                frame=next(f for f in page.frames if '/component/' in f.url)
                frame.wait_for_function('mapInstance && mapInstance.getViewports().length>0')
                assert not frame.locator('#error').is_visible()
                assert frame.evaluate('records.length')==2
                assert 'rank_label' in frame.evaluate('records[0]')
                if daily:
                    assert frame.evaluate('records.every(d=>d.forecast_date && d.obs_window_start && d.obs_window_end)')
                    assert not page.get_by_label('Observation tolerance (minutes)',exact=True).count()
                expect(page.locator('[role="tabpanel"]:visible').get_by_test_id('stImage').first).to_be_visible()
                frame.locator('#zoom-in').click()
                zoom=frame.evaluate('viewState.zoom')
                frame.wait_for_function('Math.abs(mapInstance.getViewports()[0].zoom-viewState.zoom)<1e-7')
                def pick(station):
                    xy=frame.evaluate('(id)=>{const d=records.find(d=>d.station_id===id);return mapInstance.getViewports()[0].project([d.longitude,d.latitude]);}',station)
                    frame.wait_for_function('(xy)=>mapInstance.pickObject({x:xy[0],y:xy[1],radius:4})?.object?.station_id === "B"',arg=xy)
                    box=frame.frame_element().bounding_box()
                    page.mouse.click(box['x']+xy[0],box['y']+xy[1])
                frame.frame_element().scroll_into_view_if_needed()
                pick('B')
                frame.wait_for_function('selected.has("B")')
                assert abs(frame.evaluate('viewState.zoom')-zoom)<1e-7
                page.get_by_role('tab',name='Station detail',exact=True).click()
                selector=page.get_by_test_id('stSelectbox').filter(has=page.get_by_text('Station detail',exact=True))
                expect(selector.get_by_role('combobox')).to_have_value('B')
                expect(page.locator('[role="tabpanel"]:visible').get_by_test_id('stImage').first).to_be_visible()
                page.get_by_role('tab',name='Storm evolution',exact=True).click()
                cohort_label='Use stations matched on every forecast date' if daily else 'Use stations matched at every projection'
                page.get_by_text(cohort_label,exact=True).click()
                expect(page.get_by_label(cohort_label,exact=True)).to_be_checked()
                expect(page.locator('[role="tabpanel"]:visible').get_by_test_id('stImage').first).to_be_visible()
                page.get_by_role('tab',name='Spatial snapshot',exact=True).click()
                page.get_by_label('Map display',exact=True).click()
                page.get_by_role('option',name='Threshold probability',exact=True).click()
                frame.wait_for_function('records.every(d=>Array.isArray(d.event_outline_color))')
                assert frame.evaluate('records.every(d=>d.metric_value_text.endsWith("%"))')
                assert abs(frame.evaluate('viewState.zoom')-zoom)<1e-7
                # A normal desktop viewport hid clipping in the original test.
                # Scroll over the actual map/image, not merely the page margin,
                # and require the bottom of each display to be reachable.
                page.set_viewport_size({'width':1280,'height':650})
                for tab_name in ['Spatial snapshot','Storm evolution','Station detail']:
                    page.get_by_role('tab',name=tab_name,exact=True).click()
                    panel=page.locator('[role="tabpanel"]:visible')
                    target=(frame.frame_element() if tab_name=='Spatial snapshot' else
                            panel.get_by_test_id('stImage').first)
                    main=page.get_by_test_id('stMain')
                    top=target.bounding_box()['y']
                    main.evaluate('(el,top)=>el.scrollTop+=top-100',top)
                    bounds=target.bounding_box()
                    page.mouse.move(bounds['x']+bounds['width']/2,200)
                    before=main.evaluate('(el)=>el.scrollTop')
                    page.mouse.wheel(0,250)
                    page.wait_for_function('document.querySelector(\'[data-testid="stMain"]\').scrollTop > '+str(before))
                    for _ in range(15):
                        bounds=target.bounding_box()
                        if bounds['y']+bounds['height']<=640:break
                        page.mouse.wheel(0,250)
                        page.wait_for_timeout(100)
                    bounds=target.bounding_box()
                    assert 0<bounds['y']+bounds['height']<=650,(tab_name,bounds)
                    if tab_name=='Spatial snapshot':
                        assert abs(frame.evaluate('viewState.zoom')-zoom)<1e-7
                assert not page.get_by_test_id('stException').count()
                assert not errors,errors
                browser.close()
                print(f'Storm {element} browser checks passed: map render, zoom, click-to-detail, three tabs, fixed cohort, threshold-probability map, scrolling over map and plots in a short viewport.')
        except Exception:
            log.flush();log.seek(0);print(log.read());raise
        finally:
            server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':main()
