"""Temperature bands and honest probability-event overlays on matched cases."""
from pathlib import Path
import sys
import subprocess
import shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
from color_scales import temperature_boundaries, standard_bounds, color_mapping
from maps import add_map_style_columns
from storm_visuals import snapshot_map_data, map_colorbar
from probability_outcomes import (probability_outcomes, highlight_outcomes,
    POSITIVE_EVENT,ZERO_EVENT,NO_EVENT,UNKNOWN,NO_PROBABILITY,HIGHLIGHTS)
from probability import forecast_probabilities, threshold_event


@pytest.mark.parametrize('element',['maxt','mint'])
@pytest.mark.parametrize('metric',['model_value','obs_value'])
def test_temperature_marker_and_legend_bands_use_same_five_degree_grid(element,metric):
    values=[-20.,-19.9,-15.1,-15.,-10.,0.]
    snapshot=pd.DataFrame({'station_id':list('ABCDEF'),metric:values})
    metadata=pd.DataFrame({'station_id':list('ABCDEF'),'latitude':58.,'longitude':-135.})
    limits=standard_bounds(element,metric)
    data,_,_=snapshot_map_data(snapshot,metadata,metric,limits,element)
    fig=map_colorbar(metric,limits,'Temperature','F',element=element)
    bar=fig.axes[0]._colorbar
    assert np.diff(bar.norm.boundaries).tolist()==[5.]*28
    assert bar.cmap.N==28
    assert data.fill_color.iloc[0]==data.fill_color.iloc[1]==data.fill_color.iloc[2]
    assert data.fill_color.iloc[2]!=data.fill_color.iloc[3]
    for value,marker in zip(values,data.fill_color):
        assert marker==(np.array(bar.cmap(bar.norm(value)))*255).astype(int).tolist()
    # Map Explorer uses the same bin edges for its forecast maximum maps.
    styled,_,_=add_map_style_columns(pd.DataFrame({'max_fcst':values}),'max_fcst',limits,element)
    assert styled.fill_color.iloc[0]==styled.fill_color.iloc[2]
    assert styled.fill_color.iloc[2]!=styled.fill_color.iloc[3]
    plt.close(fig)


def test_custom_temperature_endpoints_are_preserved_without_changing_error_scales():
    assert temperature_boundaries('mint','model_value',(-13,27)).tolist()==[-13,-10,-5,0,5,10,15,20,25,27]
    assert temperature_boundaries('mint','error',(-5,5)) is None
    assert temperature_boundaries('wind','model_value',(0,60)) is None
    cmap,norm=color_mapping((-5,5),['blue','white','red'])
    assert norm(0)==.5 and cmap(norm(.1))!=cmap(norm(1.))


def test_zero_tiny_nonzero_missing_and_invalid_probabilities_stay_distinct():
    snapshot=pd.DataFrame({'forecast_probability':[0,1e-8,.5,0,.5,np.nan,-.1,1.1],
        'observed_event':[1,1,0,0,np.nan,1,1,1],'obs_value':[5,5,0,0,np.nan,5,5,5]})
    before=snapshot.copy(deep=True)
    result=probability_outcomes(snapshot)
    assert result.probability_outcome.tolist()==[ZERO_EVENT,POSITIVE_EVENT,NO_EVENT,NO_EVENT,
        UNKNOWN,NO_PROBABILITY,NO_PROBABILITY,NO_PROBABILITY]
    assert result.probability_text.iloc[1]!='0%'
    result['fill_color']=[[10,20,30,210]]*len(result)
    decorated=highlight_outcomes(result,HIGHLIGHTS)
    assert decorated.event_symbol.tolist()==['!','+','','','','','','']
    assert decorated.fill_color.tolist()==result.fill_color.tolist()
    assert highlight_outcomes(result,[]).event_symbol.eq('').all()
    pd.testing.assert_frame_equal(snapshot,before)


@pytest.mark.parametrize('operator,expected',[('>=',ZERO_EVENT),('>',NO_EVENT),
    ('<=',POSITIVE_EVENT),('<',NO_EVENT)])
def test_event_outcomes_follow_shared_threshold_direction_including_equality(operator,expected):
    from config import get_percentile_columns
    frame=pd.DataFrame({c:[0.] for c in get_percentile_columns('rh').values()})
    frame['obs_value']=25.
    frame['forecast_probability']=forecast_probabilities(frame,'rh',25,operator)
    frame['observed_event']=threshold_event(frame.obs_value,25,operator).astype(float)
    assert probability_outcomes(frame).probability_outcome.iloc[0]==expected


def test_storm_probability_controls_filter_graphics_without_rerunning_verification(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from test_storm_analysis import frames,metadata
    from config import get_percentile_columns
    import storm_visuals
    m,o=frames()
    m=m[m.forecast_hour.eq(12)].copy();o=o.iloc[[0,2]].copy()
    for col in get_percentile_columns('wind').values():m.loc[m.station_id.eq('B'),col]=0.
    o['obs_wind_speed_kts']=30.
    missing=m.iloc[[1]].assign(station_id='C');m=pd.concat([m,missing],ignore_index=True)
    for model,frame in [('nbmqmd',m),('obs',o)]:
        folder=tmp_path/model/'wind';folder.mkdir(parents=True)
        frame.to_parquet(folder/'2026_05_archive.parquet',index=False)
    meta=pd.concat([metadata(),metadata().iloc[[1]].assign(station_id='C')],ignore_index=True)
    path=tmp_path/'stations.parquet';meta.to_parquet(path,index=False)
    rendered=[]
    monkeypatch.setattr(storm_visuals,'_station_map',lambda **kw:rendered.append(kw) or None)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'web_app/app.py'),default_timeout=20)
    app.secrets['local']={'archive_root':str(tmp_path),'metadata_path':str(path)}
    app.run().switch_page('pages/3_Storm_Zoom.py').run()
    app.selectbox(key='storm_Model').set_value('nbmqmd').run()
    app.selectbox(key='storm_Element').set_value('wind').run()
    next(b for b in app.button if b.label=='Generate Storm Timeseries').click().run()
    assert not app.exception and not app.error
    generation=app.session_state['storm_result']['generation']
    app.selectbox(key='storm_map_display_wind_True').set_value('Threshold probability').run()
    assert not app.exception
    records={r['station_id']:r for r in rendered[-1]['records']}
    assert records['A']['event_symbol']=='+' and records['B']['event_symbol']=='!'
    assert records['C']['probability_outcome']==UNKNOWN
    app.multiselect(key='storm_probability_highlights').set_value([ZERO_EVENT])
    app.checkbox(key='storm_probability_only_highlighted').set_value(True).run()
    assert [r['station_id'] for r in rendered[-1]['records']]==['B']
    app.multiselect(key='storm_probability_highlights').set_value([]).run()
    assert not app.exception and any('Choose at least one' in i.value for i in app.info)
    assert app.session_state['storm_result']['generation']==generation
    assert len(app.session_state['storm_result']['cases'])==3


def test_browser_layer_symbols_tooltips_and_camera_update_contract():
    if not shutil.which('node'):pytest.skip('Node.js is needed for the optional component contract check')
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let instance;
class Layer {constructor(props){this.props=props;}}
class Deck {constructor(props){this.props=props;instance=this;}setProps(p){Object.assign(this.props,p);}}
const parent={};const deck={ScatterplotLayer:Layer,TextLayer:Layer,DeckGL:Deck};
const context={console,Set,Date,Math,deck,maplibregl:{},
 document:{getElementById:()=>({addEventListener:()=>{}})},
 window:{parent,deck,maplibregl:{},addEventListener:()=>{}}};
parent.postMessage=()=>{};vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const records=[{station_id:'A',event_symbol:'+',longitude:-135,latitude:58,
 event_outline_color:[0,130,65,255],probability_outcome:'Observed event with non-zero probability',probability_text:'0.000001%'}];
const render=(data,zoom)=>context.render({source:parent,data:{type:'streamlit:render',args:{
 records:data,selected_ids:['A'],metric:'forecast_probability',initial_view:{zoom},ack_event_id:null}}});
render(records,5);assert.equal(instance.props.layers.length,2);
const text=instance.props.layers[1].props;
assert.equal(text.getText(records[0]),'+');assert.equal(text.pickable,false);assert.equal(text.fontSettings.sdf,true);
assert.ok(context.tooltip({object:records[0]}).text.includes('0.000001%'));
render(records,9);assert.equal(instance.props.viewState.zoom,5);
assert.deepEqual(Array.from(instance.props.layers[0].props.getLineColor(records[0])),[255,190,0,255]);
render([{station_id:'A'}],9);assert.equal(instance.props.layers.length,1);
'''
    source=Path(__file__).parents[1]/'web_app/station_map_frontend/map.js'
    result=subprocess.run(['node','-e',script,str(source)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
