"""Two single-run storm comparisons using the shared verification matcher."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch
from comparison import prepare_forecasts, comparison_cases
from config import get_element_config, get_percentile_columns, is_probabilistic


def compare_storm_runs(a, b, observations, model_a, model_b, element, init,
                       percentile_a=None, percentile_b=None, offset_hours=0,
                       reference_tolerance='1h', obs_source='obs', obs_tolerance='1h'):
    """Choose one nearest B run, then score only common targets against one report.

    Selecting a run once prevents different missing projections from silently
    substituting forecasts from other B runs. Equal-distance ties prefer earlier.
    """
    init = pd.to_datetime(init, utc=True).tz_convert(None)
    tolerance = pd.Timedelta(reference_tolerance)
    if tolerance < pd.Timedelta(0):
        raise ValueError('Reference tolerance must be non-negative')
    a = prepare_forecasts(a, model_a, element, percentile_a)
    a = a[a.init_time.eq(init)].copy() if not a.empty else a
    b = prepare_forecasts(b, model_b, element, percentile_b)
    desired = init + pd.Timedelta(hours=offset_hours)
    runs = pd.DataFrame({'init': b.init_time.drop_duplicates() if not b.empty else pd.Series(dtype='datetime64[ns]')})
    runs['distance'] = (runs['init']-desired).abs()
    runs = runs[runs.distance.le(tolerance)].sort_values(['distance','init'])
    if runs.empty:
        return pd.DataFrame(), dict(a_eligible=len(a), forecast_matches=0,
            a_unmatched=len(a), matched_cases=0, missing_observations=0,
            desired_b_init=desired, selected_b_init=None)
    selected = runs.iloc[0]['init']
    b = b[b.init_time.eq(selected)].copy()
    shared, diagnostics = comparison_cases(a, b, observations, model_a, model_b, element,
        percentile_a, percentile_b, obs_source=obs_source, obs_time_tolerance=obs_tolerance,
        offset_hours=offset_hours, reference_tolerance=reference_tolerance,
        lead_max=float(a.forecast_hour.max()) if not a.empty else 0)
    diagnostics.update(desired_b_init=desired, selected_b_init=selected)
    if not shared.empty:
        shared['a_error'] = shared.a_model_value-shared.obs_value
        shared['b_error'] = shared.b_model_value-shared.obs_value
        shared['absolute_error_difference'] = shared.a_error.abs()-shared.b_error.abs()
    return shared, diagnostics


def storm_comparison_summary(shared, targets, balanced=False):
    data = shared.copy()
    if balanced and not data.empty:
        counts = data.groupby('station_id').target_time.nunique()
        data = data[data.station_id.isin(counts[counts.eq(len(targets))].index)]
    rows = []
    for target in targets:
        part = data[data.target_time.eq(target)] if not data.empty else data
        row = dict(target_time=target, n=len(part))
        for side in ['a','b']:
            errors = part[f'{side}_error'] if not part.empty else pd.Series(dtype=float)
            row[f'{side}_bias'] = errors.mean()
            row[f'{side}_mae'] = errors.abs().mean()
        rows.append(row)
    return pd.DataFrame(rows)


def forecast_label(model, element, percentile):
    return model.upper() + (f' p{percentile or "50"}' if is_probabilistic(model,element) else '')


def plot_comparison_evolution(summary, label_a, label_b, units):
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    for side, label, color in [('a',label_a,'#003399'),('b',label_b,'#d97706')]:
        for ax, metric in zip(axes[:2], ['bias','mae']):
            ax.plot(summary.target_time, summary[f'{side}_{metric}'], 'o-', color=color, label=label)
    axes[0].axhline(0, color='#666666', linewidth=.7)
    axes[0].set_ylabel(f'Bias ({units})'); axes[1].set_ylabel(f'MAE ({units})')
    axes[2].plot(summary.target_time, summary.n, 'o-', color='#444444', label='Shared matched stations')
    axes[2].set_ylabel('Stations'); axes[2].set_xlabel('Shared verification target (UTC)')
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M'))
    for ax in axes:
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def plot_comparison_station(shared, station, model_a, model_b, element,
                            percentile_a, percentile_b, threshold, operator='>='):
    data = shared[shared.station_id.eq(station)].sort_values('target_time')
    if data.empty:
        return None
    cfg = get_element_config(element)
    daily = cfg.get('pairing_method') == 'date'
    duration = cfg.get('accum_hours')
    windows = []
    if duration:
        for side, color in [('a','#003399'),('b','#d97706')]:
            windows.append((f'{side.upper()} forecast window', data[f'{side}_valid_time']-pd.Timedelta(hours=duration),
                            data[f'{side}_valid_time'], color))
    if daily or duration:
        if {'obs_window_start','obs_window_end'}.issubset(data):
            windows.append(('Observed window',data.obs_window_start,data.obs_window_end,'#cc0000'))
    windows = [(label, start, end, color) for label,start,end,color in windows
               if (start.notna() & end.notna() & end.gt(start)).any()]
    if windows:
        fig, (ax, wax) = plt.subplots(2,1,figsize=(11,8),gridspec_kw={'height_ratios':[3,1.5]})
    else:
        fig, ax = plt.subplots(figsize=(11,6)); wax=None
    positions = np.arange(len(data),dtype=float)
    handles = []
    columns = get_percentile_columns(element)
    for side, model, percentile, offset, color, marker in [
            ('a',model_a,percentile_a,-.16,'#003399','s'),
            ('b',model_b,percentile_b,.16,'#d97706','D')]:
        label = f'{side.upper()}: {forecast_label(model,element,percentile)}'
        if is_probabilistic(model,element):
            required = [f'{side}_{columns[p]}' for p in ['5','25','50','75','95']]
            values = data.reindex(columns=required).apply(pd.to_numeric, errors='coerce').to_numpy()
            valid = np.isfinite(values).all(axis=1) & (np.diff(values,axis=1)>=0).all(axis=1)
            # Crossing p10/p90 also invalidates a distribution; never reorder it.
            allcols = [f'{side}_{col}' for col in columns.values() if f'{side}_{col}' in data]
            full = data[allcols].apply(pd.to_numeric, errors='coerce').to_numpy()
            for i, row in enumerate(full):
                valid[i] &= (np.diff(row[np.isfinite(row)])>=0).all()
            stats = [dict(whislo=q[0],q1=q[1],med=q[2],q3=q[3],whishi=q[4],fliers=[]) for q in values[valid]]
            if stats:
                ax.bxp(stats,positions=positions[valid]+offset,widths=.25,manage_ticks=False,
                    showfliers=False,patch_artist=True,
                    boxprops={'facecolor':color,'edgecolor':color,'alpha':.25},
                    medianprops={'color':color,'linewidth':2},
                    whiskerprops={'color':color},capprops={'color':color})
            if (~valid).any():
                ax.text(.01,.99-(.05 if side=='b' else 0),f'{side.upper()}: {(~valid).sum()} incomplete/invalid box(es) omitted.',
                        transform=ax.transAxes,va='top',fontsize=8)
            handles.append(Patch(facecolor=color,alpha=.25,label=f'{side.upper()}: {model.upper()} p25–p75 box; p5–p95 whiskers; p50 line'))
        ax.scatter(positions+offset,data[f'{side}_model_value'],marker=marker,color=color,s=25,zorder=4,label=label)
    ax.scatter(positions,data.obs_value,color='#cc0000',edgecolors='white',s=48,zorder=5,label='Shared matched observation')
    ax.axhline(threshold,color='#666666',linestyle=':',label=f'Threshold: {operator} {threshold:g} {cfg["units"]}')
    labels = [pd.Timestamp(t).strftime('%Y-%m-%d' if daily else '%m-%d\n%H:%M') for t in data.target_time]
    ax.set_xticks(positions,labels,rotation=30,ha='right'); ax.set_xlim(-.6,len(data)-.4)
    ax.set_xlabel('Forecast date used for verification' if daily else 'Forecast valid time (UTC)')
    ax.set_ylabel(f'{cfg["label"]} ({"°F" if daily else cfg["units"]})')
    ax.set_title(f'{cfg["label"]} at {station}\nA: {model_a.upper()} initialized {data.a_init_time.iloc[0]:%Y-%m-%d %H:%M} UTC; '
                 f'B: {model_b.upper()} initialized {data.b_init_time.iloc[0]:%Y-%m-%d %H:%M} UTC')
    ordinary, _ = ax.get_legend_handles_labels(); ax.legend(handles=handles+ordinary,fontsize=8,loc='best')
    ax.grid(axis='y',alpha=.25)
    if element=='rh':ax.set_ylim(0,100)
    elif duration:ax.set_ylim(bottom=-.03*max(ax.get_ylim()[1],.01))
    if wax is not None:
        for i,(label,start,end,color) in enumerate(windows):
            good = start.notna() & end.notna() & end.gt(start)
            wax.hlines(positions[good]+(i-(len(windows)-1)/2)*.18,
                mdates.date2num(pd.to_datetime(start[good]).to_numpy()),
                mdates.date2num(pd.to_datetime(end[good]).to_numpy()),color=color,linewidth=3,label=label)
        wax.set_yticks(positions,labels);wax.invert_yaxis();wax.xaxis_date()
        wax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M'))
        wax.set_xlabel('Observed measurement windows (UTC)' if daily else 'Forecast and observed accumulation windows (UTC)')
        wax.grid(alpha=.25);wax.legend(fontsize=8)
    fig.tight_layout()
    return fig
