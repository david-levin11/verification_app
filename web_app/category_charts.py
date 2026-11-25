"""Shared category controls and charts for regional and selected-site results."""
import copy
import numpy as np
import pandas as pd
from config import CATEGORY_CONFIG, get_available_category_sets, get_element_config, numeric_category
from pairing import add_category_columns


def parse_category_cutoffs(text):
    try:
        cutoffs=[float(value.strip()) for value in text.split(',')]
    except ValueError:
        raise ValueError('Enter comma-separated numbers, such as -20, 0, 20, 32, 50.') from None
    if not 1 <= len(cutoffs) <= 30:
        raise ValueError('Enter between 1 and 30 boundaries.')
    if not np.isfinite(cutoffs).all() or np.any(np.diff(cutoffs)<=0):
        raise ValueError('Boundaries must be finite numbers in strictly increasing order, without duplicates.')
    return cutoffs


def category_controls(ui,element,category_set=None):
    """Chart-only controls; never change matching, thresholds, or stored pairs."""
    import streamlit as st
    available=get_available_category_sets(element)
    if not available:return None
    category_set=category_set if category_set in available else available[0]
    with ui.expander('Chart categories',expanded=False):
        if len(available)>1:
            category_set=ui.selectbox('Category set',available,index=available.index(category_set),
                                     key=f'chart_category_set_{element}')
        default=copy.deepcopy(CATEGORY_CONFIG[category_set])
        mode=ui.selectbox('Category boundaries',['Default','Custom'],key=f'chart_category_mode_{element}_{category_set}')
        specification=default
        if mode=='Custom':
            finite=[value for value in default['bins'][1:-1] if np.isfinite(value)]
            text=ui.text_input('Upper category boundaries (comma-separated)',
                value=', '.join(f'{value:g}' for value in finite),key=f'chart_category_edges_{element}_{category_set}')
            try:
                cutoffs=parse_category_cutoffs(text)
                specification=numeric_category(cutoffs,'°F' if element in {'maxt','mint'} else get_element_config(element)['units'])
            except ValueError as exc:
                st.error(f'{exc} Showing the default categories until corrected.')
        st.caption('Each boundary belongs to the category ending at that number. Custom categories include values below the first and above the last boundary. '
                   'Changes redraw these charts without reloading data or changing event thresholds, scores, or map colors.')
        st.caption('Categories: '+'; '.join(specification['labels'].values()))
    return specification


def categorical_data(pairs,specification):
    data=add_category_columns(pairs,specification['bins'],list(specification['labels']))
    valid=data.dropna(subset=['model_category','obs_category']).copy()
    labels=list(specification['labels'])
    counts=pd.crosstab(valid.obs_category,valid.model_category).reindex(index=labels,columns=labels,fill_value=0)
    counts.index.name='observed_category';counts.columns.name='forecast_category'
    return valid,counts


def render_category_charts(pairs,context,ui,downloads,group_name,category_set=None):
    import streamlit as st
    from chart_downloads import render_chart
    from plots import plot_forecast_bias_bar_chart, plot_confusion_matrix
    specification=category_controls(ui,context['element'],category_set)
    if specification is None:
        st.info('No category definitions are available for this weather element.')
        return
    data,counts=categorical_data(pairs,specification)
    st.subheader('Categorical verification')
    st.caption(f'{len(data):,} forecast/observation pairs across {data.station_id.nunique():,} stations. '
               f'{len(pairs)-len(data):,} pairs lack a forecast or observation category and are excluded from these charts. '
               'Each pair carries equal weight; stations with more cases contribute more.')
    if data.empty:
        st.info('No paired values fall in the chart categories.')
        return
    frequency,matrix=st.tabs(['Category frequency','Confusion matrix'])
    args=(data,'obs_category','model_category',context['model'],context['obs'],group_name,
          context['start_date'],context['end_date'],context.get('forecast_projection','Selected leads'),specification['labels'])
    variable=get_element_config(context['element'])['label']
    percentile=context.get('percentile')
    if percentile is not None:variable+=f' p{percentile}'
    with frequency:
        st.caption('Category frequency answers the question: within each observed category, how often was the forecast in the same, a lower, or a higher category? '
                   'Each populated bar totals 100%; n is the number of paired cases in that observed category. Empty categories have no bar.')
        fig=plot_forecast_bias_bar_chart(*args,varname=variable)
        render_chart(fig, 'category frequency')
    with matrix:
        st.caption('The confusion matrix answers the question: which forecast and observed category combinations occurred? '
                   'Cells show percentages of all categorized pairs; the diagonal marks matching categories. Empty categories remain on both axes.')
        fig=plot_confusion_matrix(*args,varname=variable,criteria='')
        render_chart(fig, 'category confusion matrix')
    downloads.add(data,name='Categorized paired cases')
    downloads.add(counts.rename(index=specification['labels'],columns=specification['labels']).reset_index(),name='Category confusion counts')
    downloads.add_json(dict(labels=specification['labels'],bins=[str(x) if not np.isfinite(x) else x for x in specification['bins']],
                            boundary_rule='lower < value <= upper'),name='Chart category definitions')
