"""Date-based storm displays; observed windows are shown without inventing forecast windows."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from config import get_element_config, get_percentile_columns, is_probabilistic


def temperature_snapshot_label(value, cases, element):
    target = pd.Timestamp(value)
    group = cases[cases.target_time.eq(target)]
    low,high = group.forecast_hour.min(),group.forecast_hour.max()
    lead = f'+{low:g} h' if low==high else f'+{low:g}–{high:g} h'
    return f'{get_element_config(element)["label"]} for {target:%Y-%m-%d} ({lead})'


def plot_temperature_periods(cases, station, model, element, percentile=None, threshold=32, operator='>='):
    data = cases[cases.station_id.eq(station)].sort_values('target_time').copy()
    if data.empty:return None
    windows = data.dropna(subset=['obs_window_start','obs_window_end'])
    windows = windows[windows.obs_window_end.gt(windows.obs_window_start)]
    if windows.empty:
        fig,ax = plt.subplots(figsize=(11,5))
        ax_window = None
    else:
        fig,(ax,ax_window) = plt.subplots(2,1,figsize=(11,8),gridspec_kw={'height_ratios':[3,1.5]})
    positions = np.arange(len(data),dtype=float)
    probabilistic = is_probabilistic(model,element)
    if probabilistic:
        columns = get_percentile_columns(element)
        for low,high,width,color,alpha in [('5','95',.65,'#aaaaaa',.35),
                ('10','90',.45,'#99ccff',.65),('25','75',.25,'#003399',.5)]:
            if columns[low] not in data or columns[high] not in data:continue
            a,b = (pd.to_numeric(data[columns[p]],errors='coerce') for p in [low,high])
            valid = data.distribution_valid & np.isfinite(a) & np.isfinite(b)
            ax.bar(positions[valid]-.08,(b-a)[valid],bottom=a[valid],width=width,
                   color=color,alpha=alpha,label=f'p{low}–p{high}')
    label=f'{model.upper()} p{percentile or "50"}' if probabilistic else f'{model.upper()} forecast'
    ax.plot(positions-.08,data.model_value,'s',color='#000066',label=label)
    ax.plot(positions+.12,data.obs_value,'o',color='#cc0000',label='Matched observed extreme')
    ax.axhline(threshold,color='#666666',linestyle=':',linewidth=1,label=f'Event threshold: {operator} {threshold:g}°F')
    dates = [pd.Timestamp(t).strftime('%Y-%m-%d') for t in data.target_time]
    ax.set_xticks(positions,dates,rotation=30,ha='right')
    ax.set_ylabel(f'{get_element_config(element)["label"]} (°F)')
    ax.set_xlabel('Forecast date used for verification')
    ax.set_title(f'{model.upper()} {get_element_config(element)["label"]} at {station}\nInitialized {data.init_time.iloc[0]:%Y-%m-%d %H:%M} UTC')
    ax.grid(alpha=.25);ax.legend(loc='best',fontsize=8)
    if ax_window is not None:
        for position,(_,row) in enumerate(windows.iterrows()):
            ends = mdates.date2num([pd.Timestamp(row.obs_window_start).to_pydatetime(),
                                   pd.Timestamp(row.obs_window_end).to_pydatetime()])
            ax_window.hlines(position,*ends,color='#cc0000',linewidth=4)
            ax_window.plot(ends,[position,position],'|',color='#cc0000')
        ax_window.set_yticks(range(len(windows)),[pd.Timestamp(d).strftime('%Y-%m-%d') for d in windows.target_time])
        ax_window.invert_yaxis()
        ax_window.xaxis_date()
        ax_window.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M'))
        ax_window.set_ylabel('Forecast date')
        ax_window.set_xlabel('Observed measurement windows (UTC)')
        ax_window.grid(alpha=.25)
    fig.tight_layout()
    return fig
