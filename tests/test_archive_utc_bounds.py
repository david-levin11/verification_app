"""UTC observation dates must not be filtered using the host's local midnight."""
from datetime import date
from pathlib import Path
import sys
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'web_app'))
import data_loader
from comparison_loader import load_comparison_data
from comparison import comparison_cases
from storm_analysis import build_storm_cases


@pytest.mark.parametrize('element',['mint','maxt'])
@pytest.mark.parametrize('precision',['ns','us'])
def test_first_daily_observation_survives_local_zone_in_both_loaders(tmp_path,monkeypatch,element,precision):
    dates=pd.date_range('2026-02-21',periods=3,freq='D',tz='UTC').as_unit(precision)
    start=dates+pd.Timedelta(hours=12 if element=='maxt' else 0)
    endpoint=start+pd.Timedelta(hours=18)
    values=[21.92,17.96,14.]
    obs=pd.DataFrame({'stid':['PAJN']*3,'date':dates,'window_start':start,
                      'window_end':endpoint,('tmin' if element=='mint' else 'tmax'):values})
    valid=endpoint.tz_localize(None)
    init=pd.Timestamp('2026-02-21')
    model=pd.DataFrame({'station_id':['PAJN']*3,'init_time':init,'valid_time':valid,
        'forecast_hour':(valid-init).total_seconds()/3600,f'{element}_p50':[20.]*3})
    ndfd=pd.DataFrame({'station_id':['PAJN']*3,'valid_time':dates.tz_localize(None),
        'forecast_hour':(dates.tz_localize(None)-init).total_seconds()/3600,element:[20.]*3})
    for name,frame in [('obs',obs),('nbmqmd',model),('ndfd',ndfd)]:
        folder=tmp_path/name/element;folder.mkdir(parents=True)
        frame.to_parquet(folder/'2026_02_archive.parquet',index=False)
    connect=data_loader.duckdb.connect
    def alaska_connection(*args,**kwargs):
        con=connect(*args,**kwargs)
        con.execute("SET TimeZone = 'America/Anchorage'")
        return con
    monkeypatch.setattr(data_loader.duckdb,'connect',alaska_connection)
    m,o,_=data_loader.fetch_data('Storm Specific Zoom','nbmqmd','obs',date(2026,2,21),date(2026,2,23),
        ['PAJN'],[],init,{},'50',element,tmp_path,'0min')
    cases=build_storm_cases(m,o,'nbmqmd','obs',element,init,'50')
    assert len(cases)==3 and cases.obs_value.tolist()==values
    assert cases.forecast_date.iloc[0]==pd.Timestamp('2026-02-21')
    a,b,o,_=load_comparison_data(tmp_path,'ndfd','nbmqmd','obs',element,
        date(2026,2,21),date(2026,2,23),['PAJN'])
    shared,_=comparison_cases(a,b,o,'ndfd','nbmqmd',element,None,'50')
    assert len(shared)==3 and shared.obs_value.tolist()==values
