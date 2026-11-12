"""Shared map display limits. Scaling never changes scores or station selection."""
import numpy as np
import pandas as pd
from config import get_element_config


SIGNED = {'bias', 'error', 'median_error', 'absolute_error_difference'}
PROPORTIONS = {'pod', 'far', 'csi', 'event_freq_obs', 'event_freq_fcst',
               'brier_score', 'reliability_error', 'forecast_probability'}


def signed_scale(metric, difference=False):
    return difference or metric in SIGNED


def finite_values(values):
    return pd.to_numeric(pd.Series(values), errors='coerce').replace(
        [np.inf, -np.inf], np.nan).dropna()


def scale_units(element, metric, difference=False):
    if metric in {'n', 'n_prob'}: return 'cases'
    if metric in PROPORTIONS or metric == 'frequency_bias': return 'unitless'
    if metric == 'observed_percentile': return 'percentile'
    if metric == 'angular_error': return 'degrees'
    if element in {'rh', 'minrh'} and (signed_scale(metric, difference) or
            metric in {'mae', 'rmse', 'absolute_error'} or metric.startswith('width_')):
        return 'percentage points'
    return get_element_config(element)['units']


def fit_bounds(values, metric, difference=False):
    """Robust 95% limits; errors start at zero and signed scales stay symmetric."""
    values = finite_values(values)
    if values.empty: return (-1., 1.) if signed_scale(metric, difference) else (0., 1.)
    if signed_scale(metric, difference):
        bound = float(values.abs().quantile(.95))
        if bound == 0: bound = float(values.abs().max())
        bound = bound or 1.
        return -bound, bound
    if metric in {'model_value', 'obs_value', 'max_obs', 'max_fcst'}:
        low, high = float(values.quantile(.05)), float(values.quantile(.95))
        if low == high:
            low, high = min(0., float(values.min())), max(0., float(values.max()))
    else:
        low, high = 0., float(values.quantile(.95))
    if high <= low: high = low + 1.
    return low, high


def standard_bounds(element, metric, difference=False, values=()):
    """Display defaults, not acceptable-error thresholds. Values use archive units."""
    if metric in PROPORTIONS:
        return (-.25, .25) if difference else (0., 1.)
    if metric == 'frequency_bias': return (-1., 1.) if difference else (0., 2.)
    if metric == 'observed_percentile': return 0., 100.
    if metric == 'angular_error': return 0., 180.
    if metric in {'n', 'n_prob'}: return fit_bounds(values, metric, difference)
    if element.startswith('precip'):
        bias, error, amount = (.25, .5, 1.) if element == 'precip6hr' else (.5, 1., 3.)
        physical = (0., amount)
    elif element.startswith('snow'):
        factor = get_element_config(element).get('accum_hours', 6) / 6
        bias, error, physical = 2 * factor, 4 * factor, (0., 12 * factor)
    elif element in {'maxt', 'mint', 'temp2m'}:
        bias, error, physical = 5., 10., (-40., 100.)
    elif element in {'rh', 'minrh'}:
        bias, error, physical = 10., 20., (0., 100.)
    else:
        bias, error, physical = 5., 10., (0., 80. if element == 'gust' else 60.)
    if signed_scale(metric, difference): return -bias, bias
    if metric in {'mae', 'rmse', 'absolute_error'}: return 0., error
    if metric.startswith('width_'): return 0., error * 2
    return physical


def scale_controls(ui, values, element, metric, difference=False):
    """Page-local controls return the single set of limits used by map and legend."""
    import streamlit as st
    standard = standard_bounds(element, metric, difference, values)
    key = f'color_{element}_{metric}_{difference}'
    units = scale_units(element, metric, difference)
    with ui.expander('Map color scale', expanded=False):
        mode = ui.selectbox('Color scale', ['Standard', 'Fit to data', 'Custom'], key=key)
        limits = standard
        if mode == 'Fit to data':
            limits = fit_bounds(values, metric, difference)
            st.caption('Uses the 95th percentile of absolute values for signed scales; '
                       'other scales use the 95th percentile, with the 5th percentile '
                       'as the lower limit for forecast/observed values. Signed scales stay centered on zero.')
        elif mode == 'Custom':
            if signed_scale(metric, difference):
                bound = ui.number_input(f'Color limit ± ({units})', min_value=.000001,
                    value=float(standard[1]), format='%.4f', key=key+'_bound')
                limits = (-bound, bound)
            else:
                left, right = ui.columns(2)
                low = left.number_input(f'Color minimum ({units})', value=float(standard[0]),
                    format='%.4f', key=key+'_low')
                high = right.number_input(f'Color maximum ({units})', value=float(standard[1]),
                    format='%.4f', key=key+'_high')
                if not np.isfinite([low, high]).all() or low >= high:
                    st.error('Color maximum must exceed minimum. Showing the standard scale until corrected.')
                else: limits = low, high
        st.caption(f'Color limits: {limits[0]:g} to {limits[1]:g} {units}. '
                   'Limits affect colors only; all stations and their actual values remain available.')
        if mode == 'Standard' and metric in {'n', 'n_prob'}:
            st.caption('Sample-count limits adapt to the data because counts have no fixed physical range.')
    return limits


def clipped_counts(values, limits):
    values = finite_values(values)
    return int(values.lt(limits[0]).sum()), int(values.gt(limits[1]).sum())


def clipping_caption(values, limits):
    import streamlit as st
    below, above = clipped_counts(values, limits)
    if below or above:
        st.caption(f'{below:,} station values below and {above:,} above the color limits '
                   'use the end colors. Tooltips and tables retain actual values.')


SEQUENTIAL_BANDS = 5


def color_mapping(limits, colors, stepped=False):
    """Share bin edges and palette between station markers and their colorbar."""
    from matplotlib.colors import LinearSegmentedColormap, Normalize, BoundaryNorm
    cmap = LinearSegmentedColormap.from_list('station_scale', colors) if isinstance(colors, list) else colors
    if stepped:
        cmap = cmap.resampled(SEQUENTIAL_BANDS)
        norm = BoundaryNorm(np.linspace(*limits, SEQUENTIAL_BANDS + 1), cmap.N, clip=True)
    else:
        norm = Normalize(*limits)
    return cmap, norm


def colorbar(limits, label, colors, values=(), stepped=False):
    """Compact legend with both end caps; captions report actual clipped counts."""
    import matplotlib.pyplot as plt
    from matplotlib.colorbar import ColorbarBase
    cmap, norm = color_mapping(limits, colors, stepped)
    fig = plt.figure(figsize=(6, .8))
    ax = fig.add_axes([.08, .58, .84, .20])
    bar = ColorbarBase(ax, cmap=cmap, norm=norm, orientation='horizontal',
                       extend='both', extendfrac=.045, drawedges=stepped)
    bar.set_ticks(np.linspace(*limits, SEQUENTIAL_BANDS + 1 if stepped else 5))
    bar.set_label(label, fontsize=8, labelpad=3)
    bar.ax.tick_params(labelsize=7, length=2, pad=2)
    bar.outline.set_linewidth(.5)
    if stepped:
        bar.dividers.set_color('#777777')
        bar.dividers.set_linewidth(.4)
    return fig
