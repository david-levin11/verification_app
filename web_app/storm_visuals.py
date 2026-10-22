"""Storm maps with local station selection and projection evolution plots."""
import numpy as np
import json
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from page_controls import set_page_value
from comparison_plots import station_map_view
from station_map import _station_map
from storm_analysis import available_intervals


def map_colormap(metric):
    return plt.get_cmap('RdBu_r' if metric in ['observed_percentile','error','median_error'] else 'viridis')


def map_colorbar(metric, limits, label, units):
    """Use exactly the same normalization and colormap as the station markers."""
    from matplotlib.colorbar import ColorbarBase
    from matplotlib.colors import Normalize
    from matplotlib.ticker import PercentFormatter
    fig=plt.figure(figsize=(10,1.05))
    ax=fig.add_axes([.08,.55,.84,.23])
    bar=ColorbarBase(ax,cmap=map_colormap(metric),norm=Normalize(*limits),orientation='horizontal')
    if metric=='forecast_probability':
        bar.set_ticks([0,.25,.5,.75,1])
        bar.formatter=PercentFormatter(xmax=1,decimals=0)
        bar.update_ticks()
        bar.set_label(f'{label} (%)')
    else:
        if metric=='observed_percentile':bar.set_ticks([0,25,50,75,100])
        bar.set_label(f'{label} ({units})')
    return fig


def map_description(metric,label,cfg,percentile,threshold,operator):
    element=cfg['label'].lower()
    point=f'p{percentile} forecast' if percentile is not None else 'forecast'
    questions={
        'model_value':f'What {element} did the {point} predict at each station?',
        'obs_value':f'What {element} was observed near this forecast valid time?',
        'error':f'How much did the {point} overpredict or underpredict the observed {element}?',
        'absolute_error':f'How large was the {point} error, regardless of whether it was too high or too low?',
        'median_error':f'Was the middle of the forecast distribution (p50) above or below the observed {element}?',
        'observed_percentile':f'Where did the observed {element} fall within the forecast distribution?',
        'forecast_probability':f'What probability did this run assign to {element} {operator} {threshold:g} {cfg["units"]}?',
        'angular_error':'How many degrees apart were the forecast and observed wind directions?',
    }
    if metric.startswith('width_'):
        _,lo,hi=metric.split('_')
        question=f'How wide was the central {int(hi)-int(lo)}% of the forecast distribution at each station?'
    else:question=questions[metric]
    text=f'{label} answers the question: “{question}”'
    if metric in ['error','median_error']:
        text+=' Positive values mean the forecast was too high; negative values mean it was too low.'
    return text


def snapshot_map_data(snapshot, metadata, metric):
    if metadata.empty or not {'station_id','latitude','longitude'}.issubset(metadata):
        return pd.DataFrame(), None, None
    context = [c for c in ['station_id','latitude','longitude','name','mnet_id','elevation_ft'] if c in metadata]
    data = snapshot.merge(metadata[context].drop_duplicates('station_id'), on='station_id', how='left')
    for column in ['latitude','longitude',metric]:
        data[column] = pd.to_numeric(data[column], errors='coerce')
    data = data[np.isfinite(data[metric]) & data.latitude.between(-85,85) &
                data.longitude.between(-180,180)].copy()
    if data.empty:
        return data, None, None
    if metric in ['observed_percentile','forecast_probability']:
        low, high = (0.,100.) if metric=='observed_percentile' else (0.,1.)
    elif metric in ['error','median_error']:
        bound = max(float(data[metric].abs().max()), 1e-6)
        low, high = -bound, bound
    else:
        low, high = 0., max(float(data[metric].max()), 1e-6)
    cmap = map_colormap(metric)
    data['fill_color'] = [list((np.array(cmap((value-low)/(high-low)))*255).astype(int)) for value in data[metric]]
    data['point_radius'] = 7
    data['metric_value'] = data[metric]
    data['metric_value_text'] = (data.rank_label if metric=='observed_percentile' else
                                 data[metric].map(lambda value: f'{value:.0%}') if metric=='forecast_probability' else
                                 data[metric].map(lambda value: f'{value:.2f}'))
    bounds = []
    for lo_level, hi_level in available_intervals(snapshot):
        lo_col = next((c for c in data if c.endswith('_p'+lo_level)), None)
        hi_col = next((c for c in data if c.endswith('_p'+hi_level)), None)
        if lo_col and hi_col:
            for column in [lo_col, hi_col]:
                data[column] = pd.to_numeric(data[column], errors='coerce')
            bounds.append((lo_level, hi_level, lo_col, hi_col))
    data['interval_bounds'] = [', '.join(f'p{lo}–p{hi}: [{row[a]:g}, {row[b]:g}]'
        for lo,hi,a,b in bounds if pd.notna(row[a]) and pd.notna(row[b])) for _,row in data.iterrows()]
    if metric=='forecast_probability':
        data['event_outline_color'] = [[30,160,30,255] if value==1 else [160,70,160,255]
                                       if value==0 else [120,120,120,255] for value in data.observed_event]
    view = station_map_view(data)
    data['longitude'] = data.map_longitude
    return data, dict(latitude=view.latitude, longitude=view.longitude, zoom=view.zoom, pitch=0, bearing=0), (low,high)


def render_storm_map(data, metric, view, generation):
    """Use an independent component camera and selection, never shared stations."""
    key = f'storm_snapshot_map_{generation}'
    selection = st.session_state.get('storm_detail_station')
    event = _station_map(records=json.loads(data.to_json(orient='records', date_format='iso')),
        metric=metric, selected_ids=[selection] if selection else [], initial_view=view,
        ack_event_id=st.session_state.get('_storm_map_ack'), default=None, key=key)
    if isinstance(event, dict) and event.get('event_id') and event['event_id'] != st.session_state.get('_storm_map_ack'):
        st.session_state['_storm_map_ack'] = event['event_id']
        station = event.get('clicked_station_id')
        if station in data.station_id.tolist():
            set_page_value('storm','storm_detail_station',station)
        st.rerun()


def plot_evolution(summary, intervals, units):
    probabilistic = bool(intervals)
    fig, axes = plt.subplots(3 if probabilistic else 2, 1, figsize=(11,8 if probabilistic else 6), sharex=True)
    if summary.empty:
        axes[0].text(.5,.5,'No stations meet the selected cohort requirements.',ha='center',transform=axes[0].transAxes)
        return fig
    x = summary.forecast_hour
    if probabilistic:
        for lo,hi in intervals:
            label = f'p{lo}–p{hi}'
            axes[0].plot(x,summary[f'mean_width_{lo}_{hi}'],'o-',label=label)
            axes[1].plot(x,summary[f'coverage_{lo}_{hi}'],'o-',label=label)
        axes[0].set_ylabel(f'Mean interval width ({units})')
        axes[1].set_ylabel('Observations inside (%)');axes[1].set_ylim(-2,102)
        axes[-1].plot(x,summary.interval_stations,'o-',label='Common interval stations')
    else:
        axes[0].plot(x,summary.bias,'o-',label='Bias')
        axes[0].plot(x,summary.mae,'o-',label='MAE')
        axes[0].plot(x,summary.rmse,'o-',label='RMSE')
        axes[0].set_ylabel(f'Error ({units})')
    axes[-1].plot(x,summary.matched_stations,'o--',label='Matched stations')
    axes[-1].set_ylabel('Stations');axes[-1].set_xlabel('Forecast projection (hours from initialization)')
    for ax in axes:
        ax.grid(alpha=.25);ax.legend()
    fig.tight_layout()
    return fig
