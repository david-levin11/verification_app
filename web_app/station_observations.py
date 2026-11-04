"""Actual report-time overlays for storm station plumes; no verification changes."""
from datetime import date, datetime
import numpy as np
import pandas as pd
import matplotlib.dates as mdates
from config import get_element_config


def utc_time(value):
    return pd.to_datetime(value,utc=True).tz_convert(None)


def plot_bounds(start,end):
    low=utc_time(start) if start is not None else None
    high=utc_time(end) if end is not None else None
    if high is not None and isinstance(end,date) and not isinstance(end,datetime):
        high+=pd.Timedelta(days=1)-pd.Timedelta(nanoseconds=1)
    return low,high


def report_series(observations,station,element,start=None,end=None):
    """Retain every finite archived report, including zeros, at its actual time."""
    empty=pd.DataFrame(columns=['report_time','observed_value'])
    if observations is None or observations.empty:return empty
    id_column=next((c for c in ['station_id','stid'] if c in observations),None)
    value_column=next((c for c in get_element_config(element)['obs_value_candidates'] if c in observations),None)
    if id_column is None or value_column is None or 'valid_time' not in observations:return empty
    data=observations.loc[observations[id_column].astype(str).str.strip().eq(str(station).strip())]
    times=pd.to_datetime(data.valid_time,utc=True,errors='coerce').dt.tz_convert(None)
    values=pd.to_numeric(data[value_column],errors='coerce')
    result=pd.DataFrame({'report_time':times,'observed_value':values})
    keep=result.report_time.notna() & np.isfinite(result.observed_value)
    low,high=plot_bounds(start,end)
    if low is not None:keep &= result.report_time.ge(low)
    if high is not None:keep &= result.report_time.le(high)
    return result.loc[keep].sort_values('report_time',kind='stable')


def plume_positions(times):
    x=mdates.date2num(pd.to_datetime(times,utc=True).dt.tz_convert(None).to_numpy())
    gaps=np.diff(np.unique(x));gaps=gaps[gaps>0]
    spacing=float(gaps.min()) if len(gaps) else 3/24
    return x,spacing


def add_report_overlay(ax,observations,station,element,start,end):
    reports=report_series(observations,station,element,start,end)
    ax.scatter(reports.report_time,reports.observed_value,s=13,color='#b91c1c',alpha=.65,
               zorder=3,label='All observed reports (actual times)')
    return reports


def format_plume_axis(ax,positions,spacing,start=None,end=None):
    locator=mdates.AutoDateLocator(minticks=4,maxticks=10,tz='UTC')
    ax.xaxis_date();ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M',tz='UTC'))
    low,high=plot_bounds(start,end)
    # Keep boxes at a date boundary fully visible; report selection still uses
    # the exact requested dates rather than this visual padding.
    ax.set_xlim(min(mdates.date2num(low),positions.min()-.3*spacing) if low is not None else positions.min()-.3*spacing,
                max(mdates.date2num(high),positions.max()+.3*spacing) if high is not None else positions.max()+.3*spacing)
    ax.set_xlabel('Forecast valid times and actual observation report times (UTC)')
