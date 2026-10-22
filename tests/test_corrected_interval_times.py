"""End-to-end legacy repair and matching at corrected daily/accumulation endpoints."""
from datetime import date
from pathlib import Path
import sys
import pandas as pd
import pytest

ROOT=Path(__file__).parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web_app')]
from repair_local_interval_timestamps import repair, repair_in_place
from forecast_targets import forecast_target_time
from pairing import build_verification_pairs
from comparison import comparison_cases
from comparison_loader import load_comparison_data
from data_loader import fetch_data
from storm_analysis import build_storm_cases


def write(root,model,element,month,frame):
    p=root/model/element/f'{month}_archive.parquet'
    p.parent.mkdir(parents=True,exist_ok=True)
    frame.to_parquet(p,index=False)
    return p


def frames(element):
    days=pd.to_datetime(['2025-06-30','2025-07-01'])
    start=days+pd.Timedelta(hours=12 if element=='maxt' else 0)
    end=start+pd.Timedelta(hours=18)
    m=pd.DataFrame(dict(station_id=['A','A'],init_time=pd.Timestamp('2025-06-29'),valid_time=end))
    m['forecast_hour']=(m.valid_time-m.init_time).dt.total_seconds()/3600
    for p in [5,10,25,50,75,90,95]:m[f'{element}_p{p}']=[50+p/10,70+p/10]
    o=pd.DataFrame(dict(stid=['A','A'],date=days,window_start=start,window_end=end,
                        valid_time=end,**{('tmax' if element=='maxt' else 'tmin'):[55.,75.]}))
    n=pd.DataFrame(dict(station_id=['A','A'],valid_time=days,forecast_hour=(days-pd.Timestamp('2025-06-29')).total_seconds()/3600,
                        **{element:[56.,76.]}))
    return m,o,n


@pytest.mark.parametrize('element',['maxt','mint'])
def test_corrected_dates_agree_in_pairing_storm_and_both_comparison_orders(element):
    m,o,n=frames(element)
    expected=list(pd.to_datetime(['2025-06-30','2025-07-01']))
    assert forecast_target_time(m,'nbmqmd',element).tolist()==expected
    legacy=m.copy()
    legacy[['init_time','valid_time']]-=pd.Timedelta(hours=18)
    assert forecast_target_time(legacy,'nbmqmd',element).tolist()==expected
    pair=build_verification_pairs(m,o,'nbmqmd','obs',element,'50')
    assert pair.obs_value.tolist()==[55.,75.]
    storm=build_storm_cases(m,o,'nbmqmd','obs',element,'2025-06-29','50')
    assert storm.forecast_date.tolist()==expected and storm.obs_value.tolist()==[55.,75.]
    for a,b,ma,mb,pa,pb in [(m,n,'nbmqmd','ndfd','50',None),(n,m,'ndfd','nbmqmd',None,'50')]:
        cases,_=comparison_cases(a,b,o,ma,mb,element,pa,pb,reference_tolerance='0h')
        assert len(cases)==2 and cases.obs_value.tolist()==[55.,75.]
        assert cases.target_time.tolist()==expected
    earlier=m.copy()
    earlier['init_time']-=pd.Timedelta(hours=6)
    earlier['forecast_hour']+=6
    offset_cases,_=comparison_cases(n,earlier,o,'ndfd','nbmqmd',element,None,'50',offset_hours=-6)
    assert offset_cases.obs_value.tolist()==[55.,75.]
    assert offset_cases.actual_offset_hours.eq(-6).all()


@pytest.mark.parametrize('element',['maxt','mint'])
@pytest.mark.parametrize('mode',['Storm Specific Zoom','Aggregate Verification','Map Explorer'])
def test_loaders_filter_verification_dates_not_next_day_endpoint(tmp_path,element,mode):
    m,o,n=frames(element)
    write(tmp_path,'nbmqmd',element,'2025_06',m)
    write(tmp_path,'ndfd',element,'2025_06',n)
    for month,g in o.groupby(o.date.dt.strftime('%Y_%m')):write(tmp_path,'obs',element,month,g)
    loaded,reports,_=fetch_data(mode,'nbmqmd','obs',date(2025,6,30),date(2025,6,30),
        ['A'],[],pd.Timestamp('2025-06-29'),{},'50',element,tmp_path,'0min')
    pair=build_verification_pairs(loaded,reports,'nbmqmd','obs',element,'50')
    assert len(loaded)==len(pair)==1 and pair.obs_value.iloc[0]==55.
    a,b,reports,_=load_comparison_data(tmp_path,'ndfd','nbmqmd','obs',element,
        date(2025,6,30),date(2025,6,30),['A'],obs_time_tolerance='0min')
    c,_=comparison_cases(a,b,reports,'ndfd','nbmqmd',element,None,'50')
    assert len(c)==1 and c.obs_value.iloc[0]==55.


@pytest.mark.parametrize('element,hours',[('maxt',18),('mint',18),('precip6hr',6),('precip24hr',24)])
def test_repair_month_routing_values_second_duplicate_and_no_repeat(tmp_path,element,hours):
    prefix=element if element in ['maxt','mint'] else 'qpf'
    m=pd.DataFrame(dict(station_id=['A','A','B'],init_time=pd.Timestamp('2025-06-30 18:00'),
        valid_time=pd.Timestamp('2025-07-02 00:00'),forecast_hour=30,**{prefix+'_p50':[1.,2.,3.]}))
    src=tmp_path/'model';original=write(src,'nbmqmd',element,'2025_06',m)
    before=original.read_bytes()
    output=tmp_path/'corrected'
    manifest=repair(src,output,['nbmqmd'],[element])
    result=pd.read_parquet(output/'nbmqmd'/element/'2025_07_archive.parquet')
    assert manifest['status']=='COMPLETE'
    assert result[prefix+'_p50'].tolist()==[2.,3.]
    assert result.init_time.eq(m.init_time.iloc[0]+pd.Timedelta(hours=hours)).all()
    assert result.valid_time.eq(m.valid_time.iloc[0]+pd.Timedelta(hours=hours)).all()
    assert result.forecast_hour.eq(30).all() and original.read_bytes()==before
    with pytest.raises(ValueError,match='Already repaired'):
        repair(output,tmp_path/'again',['nbmqmd'],[element])


def test_in_place_backup_leaves_obs_and_wind_unchanged(tmp_path):
    m,o,_=frames('maxt')
    m[['init_time','valid_time']]-=pd.Timedelta(hours=18)
    root=tmp_path/'model'
    original=write(root,'nbmqmd','maxt','2025_06',m).read_bytes()
    obs=write(root,'obs','maxt','2025_06',o);obs_bytes=obs.read_bytes()
    wind=write(root,'nbmqmd','wind','2025_06',m);wind_bytes=wind.read_bytes()
    backup=repair_in_place(root,['nbmqmd'],['maxt'])
    assert (backup/'originals/nbmqmd/maxt/2025_06_archive.parquet').read_bytes()==original
    assert obs.read_bytes()==obs_bytes and wind.read_bytes()==wind_bytes
    with pytest.raises(FileExistsError):repair_in_place(root,['nbmqmd'],['maxt'])


@pytest.mark.parametrize('element,hours',[('precip6hr',6),('precip24hr',24)])
def test_repaired_precipitation_selects_correct_window_and_rejects_wrong_duration(tmp_path,element,hours):
    # Legacy row labels the beginning of the accumulation window.
    legacy=pd.DataFrame(dict(station_id=['A'],init_time=[pd.Timestamp('2025-06-30')-pd.Timedelta(hours=hours)],
        valid_time=[pd.Timestamp('2025-07-01')-pd.Timedelta(hours=hours)],forecast_hour=[24],qpf_p50=[.5]))
    source=tmp_path/'source';write(source,'nbmqmd',element,'2025_06',legacy)
    out=tmp_path/'out';repair(source,out,['nbmqmd'],[element])
    end=pd.Timestamp('2025-07-01')
    obs=pd.DataFrame(dict(stid=['A','A'],end_time=end,valid_time=end,
        start_time=[end-pd.Timedelta(hours=hours),end-pd.Timedelta(hours=hours+6)],precip_total=[.6,99.]))
    write(out,'obs',element,'2025_07',obs)
    m,o,_=fetch_data('Aggregate Verification','nbmqmd','obs',date(2025,7,1),date(2025,7,1),
        ['A'],[],None,{},'50',element,out,'0min')
    pair=build_verification_pairs(m,o,'nbmqmd','obs',element,'50','0min')
    assert len(pair)==1 and pair.obs_value.iloc[0]==.6
    assert pair.model_window_end.iloc[0]==end
    assert pair.model_window_start.iloc[0]==end-pd.Timedelta(hours=hours)
