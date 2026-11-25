"""The generator discovers historic marine stations by coordinates, not state/status."""
from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]))
pytest.importorskip('geopandas', reason='Metadata generation uses optional GIS dependencies')
import build_ak_station_metadata as generator


def station(identifier,latitude=58,longitude=-135,**extras):
    return dict(STID=identifier,LATITUDE=latitude,LONGITUDE=longitude,STATUS='ACTIVE',**extras)


def response(stations):
    return {'SUMMARY':{'RESPONSE_CODE':1},'STATION':stations}


def test_alaska_boxes_all_statuses_and_local_validation(monkeypatch):
    requests=[]
    responses=[response([
        station('NDBCRIXA2',STATE=None,MNET_ID=286),
        dict(station('HISTORICAL'),STATUS='INACTIVE'),
        station('NEIGHBOR',STATE='BC'),
        station('WEST',latitude=55,longitude=-179),
        station('BAD_REMOTE',latitude=40),
        station('BAD_LAT',latitude='invalid'),
        station('NAN',latitude=float('nan')),
        station('INF',longitude=float('inf')),
        station('BLANK_COORD',longitude=None),
        station(''),
    ]),response([
        station('ALEUTIAN',latitude=52,longitude=175),
        station('NDBCRIXA2',STATE=None,MNET_ID=286),
        station('EAST_DATELINE',latitude=50,longitude=180),
        station('WEST_DATELINE',latitude=73,longitude=-180),
        station('EAST_BOUNDARY',latitude=73,longitude=-129),
        station('OUTSIDE_EAST',longitude=-128.999),
        station('OUTSIDE_WEST',longitude=169.999),
        station('OUTSIDE_SOUTH',latitude=49.999),
        station('OUTSIDE_NORTH',latitude=73.001),
    ])]
    def request(url,params):
        requests.append(params)
        return responses[len(requests)-1]
    monkeypatch.setattr(generator,'request_json',request)
    frame=generator.fetch_synoptic_ak_stations('synthetic-token')
    assert [r['bbox'] for r in requests]==list(generator.ALASKA_QUERY_BOXES)
    assert all(not {'state','status','network','vars'} & set(r) for r in requests)
    assert set(frame.station_id)=={'NDBCRIXA2','HISTORICAL','NEIGHBOR','WEST','ALEUTIAN','EAST_DATELINE','WEST_DATELINE','EAST_BOUNDARY'}
    assert frame.station_id.eq('NDBCRIXA2').sum()==1
    assert frame.loc[frame.station_id.eq('HISTORICAL'),'status'].iloc[0]=='INACTIVE'
    assert pd.isna(frame.loc[frame.station_id.eq('NDBCRIXA2'),'state'].iloc[0])


@pytest.mark.parametrize('second',[{'SUMMARY':{'RESPONSE_CODE':0}}, {'SUMMARY':{'RESPONSE_CODE':1},'STATION':None}])
def test_failed_box_never_returns_a_partial_inventory(monkeypatch,second):
    responses=iter([response([station('A')]),second])
    monkeypatch.setattr(generator,'request_json',lambda *a,**k:next(responses))
    with pytest.raises(RuntimeError,match='request failed'):generator.fetch_synoptic_ak_stations('synthetic-token')


def test_empty_box_and_empty_region(monkeypatch):
    responses=iter([{'SUMMARY':{'RESPONSE_CODE':2}},response([station('ALEUTIAN',longitude=175)])])
    monkeypatch.setattr(generator,'request_json',lambda *a,**k:next(responses))
    assert generator.fetch_synoptic_ak_stations('synthetic-token').station_id.tolist()==['ALEUTIAN']
    monkeypatch.setattr(generator,'request_json',lambda *a,**k:response([station('OUTSIDE',latitude=0)]))
    with pytest.raises(RuntimeError,match='no stations with valid coordinates'):generator.fetch_synoptic_ak_stations('synthetic-token')


def test_generator_assigns_coastal_offshore_and_synoptic_wfos():
    frame=pd.DataFrame(dict(station_id=['COAST','OFFSHORE','SYNOPTIC'],
        latitude=[58.,60.,65.],longitude=[-135.,-150.,-160.],
        coastal_marine_zone_id=['PKZ021',None,None],coastal_marine_zone_wfo=['AJK',None,None],
        offshore_zone_id=[None,'PKZ399',None],offshore_zone_wfo=[None,'AFC',None],
        cwa_synoptic=[None,None,'AFG']))
    result=generator.add_station_group_helpers(generator.stations_to_gdf(frame))
    assert result.wfo_best.tolist()==['AJK','AFC','AFG']
    assert result.station_context.tolist()==['marine','marine','unassigned']
    assert result.wfo_assignment_source.tolist()==['coastal_marine_zone_wfo','offshore_zone_wfo','cwa_synoptic']
    assert result.crs.to_epsg()==4326
