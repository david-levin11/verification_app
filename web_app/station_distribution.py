"""Archived forecast quantiles and matched observations for one station."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from config import get_element_config, get_percentile_columns


def plot_station_distribution(cases, station, model, element, threshold, operator='>='):
    """Draw supplied quantiles directly; whiskers are p5/p95, not Tukey fences."""
    data = cases[cases.station_id.eq(station)].sort_values('target_time').copy()
    if data.empty:
        return None
    cfg = get_element_config(element)
    daily = cfg.get('pairing_method') == 'date'
    windowed = daily or cfg.get('accum_hours') is not None
    window_columns = [('obs_window_start', 'obs_window_end', '#cc0000', 'Observed window')]
    if cfg.get('accum_hours'):
        window_columns.insert(0, ('model_window_start', 'model_window_end', '#003399', 'Forecast window'))
    has_windows = windowed and any(
        start in data and end in data and
        (data[end].notna() & data[start].notna() & data[end].gt(data[start])).any()
        for start, end, _, _ in window_columns)
    if has_windows:
        fig, (ax, window_ax) = plt.subplots(2, 1, figsize=(11, 8),
            gridspec_kw={'height_ratios': [3, 1.5]})
    else:
        fig, ax = plt.subplots(figsize=(11, 6))
        window_ax = None
    positions = np.arange(len(data), dtype=float)
    columns = get_percentile_columns(element)
    required = [columns[p] for p in ['5', '25', '50', '75', '95']]
    values = data.reindex(columns=required).apply(pd.to_numeric, errors='coerce').to_numpy()
    valid = np.isfinite(values).all(axis=1) & (np.diff(values, axis=1) >= 0).all(axis=1)
    if 'distribution_valid' in data:
        valid &= data.distribution_valid.fillna(False).to_numpy(dtype=bool)
    statistics = [dict(whislo=q[0], q1=q[1], med=q[2], q3=q[3], whishi=q[4], fliers=[])
                  for q in values[valid]]
    if statistics:
        ax.bxp(statistics, positions=positions[valid], widths=.5, manage_ticks=False,
            showfliers=False, patch_artist=True,
            boxprops={'facecolor': '#99ccff', 'edgecolor': '#003399'},
            medianprops={'color': '#000066', 'linewidth': 2},
            whiskerprops={'color': '#003399'}, capprops={'color': '#003399'})
    observed = pd.to_numeric(data.obs_value, errors='coerce').to_numpy(dtype=float)
    matched = np.isfinite(observed)
    ax.scatter(positions[matched], observed[matched], color='#cc0000', edgecolors='white',
               linewidths=.6, s=45, zorder=4, label='Matched observation')
    ax.axhline(threshold, color='#666666', linestyle=':', linewidth=1,
               label=f'Event threshold: {operator} {threshold:g} {cfg["units"]}')
    if (~valid).any():
        ax.text(.01, .99, f'{(~valid).sum()} period(s) without a complete, valid p5/p25/p50/p75/p95 set; boxes omitted.',
                transform=ax.transAxes, va='top', fontsize=8)
    labels = [pd.Timestamp(t).strftime('%Y-%m-%d' if daily else '%m-%d\n%H:%M')
              for t in data.target_time]
    if not daily:
        labels = [f'{label}\n+{lead:g} h' for label, lead in zip(labels, data.forecast_hour)]
    ax.set_xticks(positions, labels, rotation=30, ha='right')
    ax.set_xlim(-.6, len(data)-.4)
    ax.set_xlabel('Forecast date used for verification' if daily else 'Forecast valid time (UTC) and projection')
    ax.set_ylabel(f'{cfg["label"]} ({"°F" if daily else cfg["units"]})')
    ax.set_title(f'{model.upper()} {cfg["label"]} at {station}\nInitialized {data.init_time.iloc[0]:%Y-%m-%d %H:%M} UTC')
    handles, legend_labels = ax.get_legend_handles_labels()
    ax.legend([Patch(facecolor='#99ccff', edgecolor='#003399'),
               Line2D([], [], color='#003399', marker='|'),
               Line2D([], [], color='#000066', linewidth=2)] + handles,
              ['p25–p75 box', 'p5–p95 whiskers', 'p50 median'] + legend_labels,
              loc='best', fontsize=8)
    ax.grid(axis='y', alpha=.25)
    if element == 'rh':
        ax.set_ylim(0, 100)
    elif cfg.get('accum_hours'):
        ax.set_ylim(bottom=-.03*max(ax.get_ylim()[1], .01))
    if window_ax is not None:
        for start, end, color, label in window_columns:
            if start not in data or end not in data:
                continue
            eligible = data[start].notna() & data[end].notna() & data[end].gt(data[start])
            if not eligible.any():
                continue
            offset = -.12 if start.startswith('model') else .12
            window_ax.hlines(positions[eligible]+offset,
                mdates.date2num(pd.to_datetime(data.loc[eligible, start]).to_numpy()),
                mdates.date2num(pd.to_datetime(data.loc[eligible, end]).to_numpy()),
                color=color, linewidth=3, label=label)
        window_ax.set_yticks(positions, labels)
        window_ax.invert_yaxis()
        window_ax.xaxis_date()
        window_ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M'))
        window_ax.set_xlabel('Observed measurement windows (UTC)' if daily else 'Forecast and observed accumulation windows (UTC)')
        window_ax.grid(alpha=.25)
        window_ax.legend(fontsize=8)
    fig.tight_layout()
    return fig
