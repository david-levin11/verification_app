"""Optional wind-direction displays for a saved model comparison."""
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
from wind_verification import (DIRECTION_LABELS, direction_exceedance,
                               grouped_direction_scores)
from comparison_plots import station_difference_map


def render_direction_comparison(result, ui, label_a, label_b):
    saved = result['context']
    if not saved.get('verify_direction'):
        return
    direction = result['direction_result']
    cases, diagnostics = direction['cases'], direction['diagnostics']
    st.subheader('Wind direction comparison')
    st.caption(f"Observed wind speed ≥ {saved['direction_min_speed']:g} kt. This uses its own shared cases, independently of the speed-score minimum. Both models use the direction from the same matched observation report.")
    if diagnostics['input_cases'] == 0:
        st.info('No matched cases are available for wind direction verification.')
        return
    if diagnostics['missing_fields']:
        names = {'a_forecast_direction': label_a, 'b_forecast_direction': label_b,
                 'observed_direction': 'the observation archive'}
        missing = ', '.join(names[c] for c in diagnostics['missing_fields'])
        st.info(f'Wind direction verification is unavailable: no direction field in {missing}. Wind-speed verification remains available. Speed percentiles do not supply forecast direction.')
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Shared direction cases', f'{len(cases):,}')
    c2.metric('Missing or invalid directions', f"{diagnostics['invalid_directions']:,}")
    c3.metric('Below direction speed minimum or calm obs', f"{diagnostics['below_observed_minimum_or_calm']:,}")
    c4.metric('Nonpositive forecast speed', f"{diagnostics['nonpositive_forecast_speed']:,}")
    st.caption('Exclusions are counted sequentially. Direction scores require valid directions and positive observed and forecast speeds for both models. Calm forecasts remain eligible for wind-speed scores.')
    if cases.empty:
        st.info('No shared cases remain for wind direction verification. Check direction coverage and the minimum observed speed.')
        return
    threshold = saved['direction_error_threshold']
    scores = direction['scores'].copy()
    scores['label'] = scores['label'].replace({'Angular error exceeding threshold (%)': f'Error > {threshold:g}° (%)'})
    scores['better'] = scores.better.replace({'A': label_a, 'B': label_b})
    st.dataframe(scores[['label', 'a', 'b', 'difference', 'better']].rename(columns={
        'label': 'Direction metric', 'a': label_a, 'b': label_b,
        'difference': 'A − B', 'better': 'Better'}), hide_index=True, use_container_width=True)
    st.caption('Absolute angular error ranges from 0° to 180°. Exceedance is strictly greater than the chosen threshold; lower is better for all direction metrics. Percentage differences are percentage points. “Better” is descriptive, not a significance test.')
    curves = direction_exceedance(cases)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for side, label, color in [('a', label_a, '#2166ac'), ('b', label_b, '#b35806')]:
        axes[0].plot(curves.threshold, curves[side], label=label, color=color)
        axes[1].hist(cases[f'{side}_angular_error'], bins=np.arange(0, 181, 15),
            weights=np.full(len(cases), 100 / len(cases)), histtype='step',
            linewidth=2, label=label, color=color)
    axes[0].axvline(threshold, color='gray', linestyle='--', label=f'{threshold:g}° threshold')
    axes[0].set(xlim=(0, 180), ylim=(0, 100), xlabel='Angular error threshold (°)', ylabel='Cases with error > threshold (%)')
    axes[1].set(xlim=(0, 180), xlabel='Absolute angular error (°)', ylabel='Cases (%)')
    for ax in axes:
        ax.grid(alpha=.25); ax.legend()
    fig.tight_layout(); st.pyplot(fig); plt.close(fig)
    metric = ui.selectbox('Direction metric for breakdowns', list(DIRECTION_LABELS),
        format_func=lambda m: DIRECTION_LABELS[m], key='compare_direction_display_metric')
    lead_tab, station_tab, data_tab = st.tabs(['Direction by lead time', 'Direction by station', 'Direction paired data'])
    with lead_tab:
        table = grouped_direction_scores(cases, 'lead_day', threshold)
        data = table[table.metric.eq(metric)]
        fig, ax = plt.subplots(figsize=(10, 4))
        for side, label, marker, color in [('a', label_a, 'o', '#2166ac'), ('b', label_b, 's', '#b35806')]:
            ax.plot(data.lead_day, data[side], marker=marker, label=label, color=color)
        ax.set(xlabel='Model A forecast day', ylabel=DIRECTION_LABELS[metric])
        ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
        st.pyplot(fig); plt.close(fig)
        st.dataframe(data[['lead_day', 'n', 'a', 'b', 'difference']].rename(columns={
            'lead_day':'A forecast day', 'n':'Shared cases', 'a':label_a, 'b':label_b, 'difference':'A − B'}), hide_index=True)
    with station_tab:
        table = grouped_direction_scores(cases, 'station_id', threshold)
        minimum = ui.number_input('Minimum direction cases per station', 1, 10000, 10, key='compare_direction_min_cases')
        deck, _ = station_difference_map(table, result['metadata'], metric, label_a, label_b, minimum)
        if deck is None:
            st.info('A direction map needs station coordinates and enough shared direction cases.')
        else:
            st.caption(f'Blue: {label_a} better. Orange: {label_b} better. White: similar.')
            st.pydeck_chart(deck, use_container_width=True)
        st.dataframe(table[table.metric.eq(metric)][['station_id', 'n', 'a', 'b', 'difference']].rename(columns={
            'station_id':'Station', 'n':'Shared cases', 'a':label_a, 'b':label_b, 'difference':'A − B'}), hide_index=True)
    with data_tab:
        columns = ['station_id', 'target_time', 'a_init_time', 'b_init_time',
            'a_forecast_hour', 'b_forecast_hour', 'actual_offset_hours',
            'a_model_value', 'b_model_value', 'obs_value', 'a_forecast_direction',
            'b_forecast_direction', 'observed_direction', 'a_angular_error', 'b_angular_error',
            'obs_valid_time', 'obs_time_offset_minutes']
        st.dataframe(cases[[c for c in columns if c in cases]].head(1000), hide_index=True)
    st.download_button('Download direction paired cases (CSV)', cases.to_csv(index=False),
        file_name='wind_direction_cases.csv', mime='text/csv', key='compare_direction_download')
    st.download_button('Download direction scorecard (CSV)', direction['scores'].to_csv(index=False),
        file_name='wind_direction_scores.csv', mime='text/csv', key='compare_direction_scores_download')
