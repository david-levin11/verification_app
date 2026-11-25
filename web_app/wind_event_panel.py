"""Display the wind subset and the compass-sector verification on either page."""

import matplotlib.pyplot as plt
import streamlit as st
from wind_verification import filter_wind_events
from wind_direction_plots import sector_error_rose, sector_heatmap


def apply_wind_subset(cases, context, downloads):
    try:
        filtered = filter_wind_events(
            cases, context['minimum_observed_speed'], context['observed_sectors']
        )
    except ValueError as exc:
        st.warning(str(exc))
        downloads.stop()
    counts = dict(paired=len(cases), retained=len(filtered))
    if filtered.empty:
        show_wind_subset(context, counts)
        st.warning('No paired cases remain. Check the archive coverage and event filters.')
        downloads.stop()
    return filtered, counts


def show_wind_subset(context, counts):
    filters = []
    if (minimum := context.get('minimum_observed_speed')) is not None:
        name = 'gust' if context['element'] == 'gust' else 'wind speed'
        filters.append(f'Observed {name} ≥ {minimum:g} kt')
    if sectors := context.get('observed_sectors'):
        filters.append(f"Observed direction in {', '.join(sectors)}")
    if filters and counts:
        st.caption(f"{' · '.join(filters)}. Retained {counts['retained']:,} of {counts['paired']:,} paired cases.")


def show_compass_agreement(context, summary, downloads):
    if not context.get('verify_direction'):
        return
    st.subheader('Wind Direction Verification')
    if summary is None:
        st.info('Direction scores require valid observed and forecast directions on the same non-calm paired cases.')
        return
    if 'sector_errors' not in summary:
        st.info('Run verification again to see the direction charts for this selection.')
        return

    n = summary['n']
    columns = st.columns(4)
    for column, key, label in zip(columns, ('same', 'adjacent', 'more_than_one', 'opposite'),
                                  ('Same sector', 'One sector apart', 'More than one apart', 'Opposite sector')):
        count = summary[key]
        column.metric(label, f'{count/n:.1%}', delta=f'{count:,} pairs', delta_color='off', border=True)
    st.caption(f'{n:,} valid direction pairs. Mean absolute angular error was {summary["angular_mae"]:.1f}°. '
               'Opposite sectors are four bins apart and count toward “More than one apart.”')

    prefix = downloads.page
    matrix = summary['matrix']
    misses = summary['miss_cases']
    sector_columns = ['observed_sector', 'forecast_sector']
    options = list(misses[sector_columns].drop_duplicates().itertuples(index=False, name=None))
    chart_key = f'{prefix}_direction_heatmap'
    detail_key = f'{prefix}_direction_pair'

    def select_sector_pair():
        points = st.session_state[chart_key]['selection'].get('sector_pair', [])
        if points:
            pair = tuple(points[0][field] for field in sector_columns)
            st.session_state[detail_key] = pair if pair in options else None

    chart_column, rose_column = st.columns([3, 2])
    with chart_column:
        mode = st.radio('Heatmap values', ['Pair counts', 'Percent within observed sector'],
                        horizontal=True, key=f'{prefix}_direction_heatmap_units')
        st.vega_lite_chart(sector_heatmap(matrix, mode != 'Pair counts'), width='stretch',
                           key=chart_key, on_select=select_sector_pair)
        if options:
            st.caption('Select a cell with a difference of two or more sectors to view its paired cases.')
    with rose_column:
        st.markdown('**Signed sector error**')
        fig = sector_error_rose(summary['sector_errors'])
        st.pyplot(fig)
        plt.close(fig)
        st.caption('Positive means the forecast is clockwise from the observation. '
                   'The radius shows the share of valid pairs.')

    if options:
        if st.session_state.get(detail_key) not in options:
            st.session_state.pop(detail_key, None)
        pair = st.selectbox('Sector pair to inspect', options, index=None, key=detail_key,
                            format_func=lambda pair: f'Forecast {pair[1]} / Observed {pair[0]}')
        if pair is not None:
            detail = misses.loc[misses.observed_sector.eq(pair[0]) & misses.forecast_sector.eq(pair[1])]
            st.caption(f'{len(detail):,} paired cases. Showing up to 100 below.')
            st.dataframe(detail.head(100), hide_index=True)
            downloads.add(detail, name=f'Wind direction cases forecast {pair[1]} observed {pair[0]}')

    downloads.add(matrix.rename_axis('Observed sector').reset_index(), name='Wind direction sector counts')
    downloads.add({key: value for key, value in summary.items() if key not in
                   ('matrix', 'sector_errors', 'miss_cases')}, name='Wind direction summary')
