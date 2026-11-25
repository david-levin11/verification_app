"""Display the wind subset and the compass-sector verification on either page."""

import streamlit as st
from wind_verification import filter_wind_events


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
    n = summary['n']
    columns = st.columns(3)
    for column, key, label in zip(columns, ('same', 'opposite', 'other'),
                                  ('Same sector', 'Opposite sector', 'Other sector')):
        count = summary[key]
        column.metric(label, f'{count/n:.1%}', border=True)
    st.caption(f'{n:,} valid direction pairs. Mean absolute angular error was {summary["angular_mae"]:.1f}°. '
               'Opposite sectors are four bins apart, such as NE and SW.')
    downloads.add(summary['matrix'].rename_axis('Observed sector').reset_index(), name='Wind direction sector counts')
    downloads.add({key: value for key, value in summary.items() if key != 'matrix'}, name='Wind direction summary')
