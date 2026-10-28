"""Storm station totals displayed over their actual accumulation windows."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from config import get_element_config, get_percentile_columns, is_probabilistic


def plot_accumulation_periods(cases, station, model, element, percentile=None, threshold=1., operator='>='):
    data=cases[cases.station_id.eq(station)].sort_values('valid_time')
    if data.empty:return None
    cfg=get_element_config(element)
    fig,ax=plt.subplots(figsize=(11,6))
    probabilistic=is_probabilistic(model,element)
    label=f'{model.upper()} p{percentile or "50"}' if probabilistic else f'{model.upper()} forecast'
    for value,start,end,color,name,marker in [
        ('model_value','model_window_start','model_window_end','#000066',label,'s'),
        ('obs_value','obs_window_start','obs_window_end','#cc0000','Matched observed total','o')]:
        shown=False
        for _,row in data.iterrows():
            if pd.isna(row[value]) or pd.isna(row[start]) or pd.isna(row[end]):continue
            ends=mdates.date2num([pd.Timestamp(row[start]).to_pydatetime(),pd.Timestamp(row[end]).to_pydatetime()])
            ax.hlines(row[value],*ends,color=color,alpha=.65,
                      linewidth=4 if value=='model_value' else 1.5,
                      linestyles='solid' if value=='model_value' else 'dashed')
            ax.plot(ends[-1],row[value],marker,color=color,
                    markersize=6 if value=='model_value' else 4,label=None if shown else name)
            shown=True
    if probabilistic:
        columns=get_percentile_columns(element)
        for lo,hi,width,color in [('5','95',8,'#cccccc'),('10','90',5,'#99ccff'),('25','75',2,'#003399')]:
            if columns[lo] not in data or columns[hi] not in data:continue
            a,b=(pd.to_numeric(data[columns[p]],errors='coerce') for p in [lo,hi])
            valid=data.distribution_valid & np.isfinite(a) & np.isfinite(b)
            ax.vlines(data.loc[valid,'valid_time'],a[valid],b[valid],color=color,linewidth=width,
                      alpha=.65,label=f'p{lo}–p{hi}')
    ax.axhline(threshold,color='#666666',linestyle=':',label=f'Event threshold: {operator} {threshold:g} {cfg["units"]}')
    ax.set_ylabel(f'{cfg["label"]} ({cfg["units"]})')
    ax.set_xlabel('Accumulation windows and endpoints (UTC)')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M'))
    ax.set_title(f'{model.upper()} {cfg["label"]} at {station}\nInitialized {data.init_time.iloc[0]:%Y-%m-%d %H:%M} UTC')
    # Leave room below the zero line so dry-period markers are fully visible.
    ax.set_ylim(bottom=-.03*max(ax.get_ylim()[1],.01))
    ax.grid(alpha=.25);ax.legend(loc='best',fontsize=8)
    fig.tight_layout()
    return fig
