"""Shared threshold probabilities and scores from archived forecast quantiles.

Between distinct quantiles the CDF is linear. Outside the archived range it
holds the nearest percentile probability (no unsupported 0/100% tail claims).
Tied quantiles define a jump: < uses its lower edge and <= its upper edge.
All-equal quantiles are explicitly approximated as a point mass. Crossing
quantiles are invalid, rather than silently reordered.
"""
import numpy as np
import pandas as pd
import json
from config import get_percentile_columns

OPERATORS = (">=", ">", "<=", "<")


def threshold_event(values, threshold, operator=">="):
    if operator not in OPERATORS:
        raise ValueError(f"Unsupported threshold operator: {operator}")
    return {">=": values.ge, ">": values.gt,
            "<=": values.le, "<": values.lt}[operator](threshold)


def quantile_probability(values, levels, threshold, operator=">="):
    """Approximate P(X operator threshold); missing/crossing rows return NaN."""
    if operator not in OPERATORS:
        raise ValueError(f"Unsupported threshold operator: {operator}")
    x = np.asarray(values, dtype=float)
    p = np.asarray(levels, dtype=float)
    valid = np.isfinite(x) & np.isfinite(p)
    x, p = x[valid], p[valid]
    if (len(x) < 2 or not np.isfinite(threshold)
            or np.any(np.diff(p) <= 0) or np.any((p <= 0) | (p >= 1))
            or np.any(np.diff(x) < 0)):
        return np.nan
    if np.all(x == x[0]):
        return float(threshold_event(pd.Series([x[0]]), threshold, operator).iloc[0])
    # >= is the complement of <; > is the complement of <=.
    strict_cdf = operator in ("<", ">=")
    equal = np.flatnonzero(x == threshold)
    if len(equal):
        cdf = p[equal[0] if strict_cdf else equal[-1]]
    elif threshold < x[0]:
        cdf = p[0]
    elif threshold > x[-1]:
        cdf = p[-1]
    else:
        right = np.searchsorted(x, threshold, side="right")
        left = right - 1
        cdf = p[left] + (p[right] - p[left]) * (
            (threshold - x[left]) / (x[right] - x[left]))
    return float(1 - cdf if operator in (">", ">=") else cdf)


def forecast_probability_details(frame, element, threshold, operator=">="):
    """Use exact archived member events; approximate only unarchived events."""
    if operator not in OPERATORS:raise ValueError(f'Unsupported threshold operator: {operator}')
    columns = get_percentile_columns(element)
    available = [(col, float(level) / 100)
                 for level, col in columns.items() if col in frame.columns]
    probability=pd.Series(np.nan,index=frame.index,dtype=float)
    source=pd.Series('quantile approximation',index=frame.index,dtype=object)
    if len(available)>=2:
        cols, levels = zip(*available)
        values = frame[list(cols)].apply(pd.to_numeric, errors="coerce")
        probability[:]=[quantile_probability(row,levels,threshold,operator) for row in values.to_numpy()]
    event_column=f'prob_{"gt" if operator==">" else "lt"}_{threshold:g}' if operator in ['>','<'] else None
    if '_forecast_model' not in frame or not frame['_forecast_model'].eq('refs').any():
        return pd.DataFrame({'forecast_prob':probability,'probability_source':source},index=frame.index)
    for position,(_,row) in enumerate(frame.iterrows()):
        if row.get('_forecast_model')!='refs':continue
        eligible=row.get('ensemble_eligible',False)
        if pd.isna(eligible) or not eligible:
            probability.iloc[position]=np.nan;source.iloc[position]='incomplete ensemble';continue
        configured=False
        recipe=row.get('statistics_config')
        if isinstance(recipe,str):
            try:
                settings=json.loads(recipe)
                configured=settings.get('operator')==operator and any(
                    float(t)==float(threshold) for t in settings.get('thresholds',[]))
            except (ValueError,TypeError,AttributeError):
                probability.iloc[position]=np.nan;source.iloc[position]='invalid probability recipe';continue
        else:
            configured=event_column in frame and row.get('probability_operator')==operator
        if configured and event_column:
            value=pd.to_numeric(pd.Series([row.get(event_column,np.nan)]),errors='coerce').iloc[0]
            probability.iloc[position]=value if np.isfinite(value) and 0<=value<=1 else np.nan
            source.iloc[position]='archived member probability'
    return pd.DataFrame({'forecast_prob':probability,'probability_source':source},index=frame.index)


def forecast_probabilities(frame, element, threshold, operator=">="):
    return forecast_probability_details(frame,element,threshold,operator).forecast_prob


def probability_cases(frame, element, threshold, operator=">=", obs_col="obs_value"):
    observed = pd.to_numeric(frame[obs_col], errors="coerce")
    result = forecast_probability_details(frame,element,threshold,operator)
    result['observed_event']=threshold_event(observed,threshold,operator).astype(float)
    result.loc[~np.isfinite(observed), "observed_event"] = np.nan
    return result.dropna()


def reliability_table(cases):
    data = cases.copy()
    data["prob_bin"] = pd.cut(data["forecast_prob"],
                             np.linspace(0, 1, 11), include_lowest=True)
    return (data.groupby("prob_bin", observed=False)
            .agg(mean_forecast=("forecast_prob", "mean"),
                 observed_freq=("observed_event", "mean"),
                 count=("observed_event", "count"))
            .reset_index().query("count > 0"))


def probability_scores(frame, element, threshold, operator=">=", obs_col="obs_value"):
    cases = probability_cases(frame, element, threshold, operator, obs_col)
    if cases.empty:
        return {"n_prob": 0, "brier_score": np.nan, "reliability_error": np.nan}
    table = reliability_table(cases)
    return {
        "n_prob": len(cases),
        "brier_score": ((cases.forecast_prob - cases.observed_event) ** 2).mean(),
        # Binned reliability component: weighted squared calibration error.
        "reliability_error": np.average(
            (table.mean_forecast - table.observed_freq) ** 2, weights=table["count"]),
    }

