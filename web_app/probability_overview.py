"""Probability map explanations and a pooled overview of the completed map run."""
import numpy as np
from probability import probability_cases, summarize_probability_cases, reliability_table

PROBABILITY_MAP_METRICS={
    'n_prob','brier_score','reliability_error','probability_bias_pp',
    'mean_probability_pct','prob_observed_frequency_pct',
    'zero_probability_events','zero_probability_event_rate_pct',
}
EXPLANATIONS={
    'n_prob':'Probability case count answers the question: how many valid forecast probabilities had matched observations?',
    'brier_score':'Brier score answers the question: how close were the probabilities to what occurred? Lower is better; 0 is perfect. It measures overall probability error, rather than calibration alone.',
    'reliability_error':'Reliability error answers the question: how close were predicted probabilities to observed frequencies in 10% probability bins? Lower is better; small samples can be noisy.',
    'probability_bias_pp':'Mean probability minus observed event frequency answers the question: did the guidance assign probabilities that were too high or too low on average? Positive means too high, negative means too low, in percentage points. Opposing errors across probability bins can cancel; inspect the reliability plot too.',
    'mean_probability_pct':'Mean forecast probability answers the question: what chance did the guidance assign to the threshold event on average?',
    'prob_observed_frequency_pct':'Observed event frequency answers the question: how often did the threshold occur among cases with a valid forecast probability and matched observation?',
    'zero_probability_events':'Zero-probability event count answers the question: how many observed threshold events were assigned exactly zero probability? Counts depend on sample size.',
    'zero_probability_event_rate_pct':'Zero-probability event rate answers the question: what percentage of all observed threshold events were assigned exactly zero probability? The denominator is observed events among valid probability cases. Sites with no observed events have an undefined rate and are omitted from this map.',
}


def build_probability_overview(merged,element,threshold,operator):
    frame=merged.reset_index(drop=True)
    cases=probability_cases(frame,element,threshold,operator)
    cases['station_id']=frame.loc[cases.index,'station_id']
    return cases


def probability_map_rows(metrics,metric,minimum):
    """Display filter only; retain unfiltered cases for the network overview."""
    if metric not in PROBABILITY_MAP_METRICS:return metrics.copy()
    return metrics.loc[metrics.n_prob.ge(minimum)].copy()


def render_probability_overview(cases,context,downloads):
    import streamlit as st
    import matplotlib.pyplot as plt
    from plots import plot_threshold_reliability
    from forecast_archive import probability_description
    st.subheader('Probability verification: all sites in this run')
    st.caption('This overview pools all valid matched probability cases in the completed Verification Overview run, including sites without map coordinates. '
               'Stations with more cases contribute more weight. Clicking stations or changing the map sample minimum does not change this overview. '
               'Use Selected-Site Verification to investigate selected stations.')
    if cases.empty:
        st.info('No valid forecast probabilities with matched observations are available for this run.')
        return
    summary=summarize_probability_cases(cases)
    left,middle,right=st.columns(3)
    left.metric('Probability cases',f"{summary['n_prob']:,}")
    middle.metric('Observed events',f"{summary['prob_observed_events']:,}")
    right.metric('Brier score',f"{summary['brier_score']:.4f}")
    left,middle,right=st.columns(3)
    left.metric('Mean forecast probability',f"{summary['mean_probability_pct']:.1f}%")
    middle.metric('Observed event frequency',f"{summary['prob_observed_frequency_pct']:.1f}%")
    right.metric('Probability minus frequency',f"{summary['probability_bias_pp']:+.1f} pp")
    rate=summary['zero_probability_event_rate_pct']
    st.caption(f"{summary['zero_probability_events']:,} observed events were assigned exactly zero probability out of "
               f"{summary['prob_observed_events']:,} observed events "
               +(f"({rate:.1f}%). " if np.isfinite(rate) else '(rate undefined: no observed events). ')
               +f"There were {summary['n_zero_probability']:,} zero-probability forecasts in total. "
               'Small non-zero probabilities remain non-zero; unavailable probabilities and missing observations are excluded.')
    st.caption('Reliability answers the question: when the model assigned a given probability, how often did the event occur? '
               'Bars show sample counts in 10% probability bins; sparse bins provide limited evidence. '
               +probability_description(context['model']=='refs'))
    fig=plot_threshold_reliability(None,context['threshold'],context['model'],context['obs'],
        f"All {cases.station_id.nunique():,} sites in map run",context['start_date'],context['end_date'],
        context['element'],threshold_operator=context['threshold_operator'],probability_data=cases)
    st.pyplot(fig);plt.close(fig)
    downloads.add(cases,name='Map probability cases')
    downloads.add(reliability_table(cases),name='Map reliability bins')
    downloads.add_json(summary,name='Map probability summary')
