"""Describe a single forecast probability against its matched threshold event."""
import numpy as np
import pandas as pd


POSITIVE_EVENT='Observed event with non-zero probability'
ZERO_EVENT='Observed event with zero probability'
NO_EVENT='Threshold not observed'
UNKNOWN='No matched observation'
NO_PROBABILITY='Probability unavailable'
HIGHLIGHTS=[POSITIVE_EVENT,ZERO_EVENT]


def probability_outcomes(snapshot):
    """Zero means exactly zero, not a rounded small probability or missing value."""
    data=snapshot.copy()
    probability=pd.to_numeric(data.forecast_probability,errors='coerce')
    event=pd.to_numeric(data.observed_event,errors='coerce')
    valid=np.isfinite(probability) & probability.between(0,1)
    known=event.isin([0,1])
    if 'obs_value' in data:known &= np.isfinite(pd.to_numeric(data.obs_value,errors='coerce'))
    status=pd.Series(UNKNOWN,index=data.index,dtype=object)
    status.loc[known & event.eq(0)]=NO_EVENT
    status.loc[known & event.eq(1) & probability.gt(0)]=POSITIVE_EVENT
    status.loc[known & event.eq(1) & probability.eq(0)]=ZERO_EVENT
    status.loc[~valid]=NO_PROBABILITY
    data['probability_outcome']=status
    data['probability_text']=probability.map(lambda p:f'{p*100:.6g}%' if np.isfinite(p) and 0<=p<=1 else 'Unavailable')
    return data


def highlight_outcomes(data,selected):
    """Annotate only selected outcomes; never replace probability fill colors."""
    data=data.copy()
    active=data.probability_outcome.isin(selected)
    data['event_outline_color']=[
        [0,130,65,255] if on and value==POSITIVE_EVENT else
        [210,40,40,255] if on and value==ZERO_EVENT else
        [120,120,120,180]
        for on,value in zip(active.to_numpy(),data.probability_outcome)]
    data['event_symbol']=[('+' if status==POSITIVE_EVENT else '!') if on else ''
                          for on,status in zip(active.to_numpy(),data.probability_outcome)]
    return data
