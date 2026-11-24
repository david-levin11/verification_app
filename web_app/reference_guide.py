"""Advisory cycle examples; matching continues to use actual archived references."""
from storm_initialization import initialization_hours, QMD_NBM_ELEMENTS
from page_controls import set_page_value


def typical_hours(model,element):
    # Operational archive schedule supplied by the app owner. NDFD references
    # may differ; these hours are advice, never an archive/matching restriction.
    return [0,12] if model=='ndfd' else initialization_hours(model,element)


def cycle_matches(hours_a,hours_b,offset,tolerance):
    """Closest nominal B cycle around each A hour, preserving day rollover."""
    candidates=[day*24+hour for day in range(-5,6) for hour in hours_b]
    rows=[]
    for hour in hours_a:
        desired=hour+offset
        nearest=min(candidates,key=lambda value:(abs(value-desired),value))
        rows.append(dict(a_hour=hour,b_hour=nearest%24,b_day=nearest//24,
            actual_offset=nearest-hour,error=nearest-desired,
            compatible=abs(nearest-desired)<=tolerance+1e-9))
    return rows


def cycle_label(hour,day=0):
    prefix='same day' if day==0 else 'previous day' if day==-1 else 'next day' if day==1 else f'{abs(day)} days '+('earlier' if day<0 else 'later')
    return f'{prefix} {hour:02d}Z'


def earlier_offsets(a_hour,hours_b):
    candidates=sorted([day*24+hour for day in range(-3,1) for hour in hours_b if day*24+hour<=a_hour],reverse=True)
    return [value-a_hour for value in candidates[:4]]


def apply_offset(value):
    set_page_value('compare','compare_use_offset',True)
    set_page_value('compare','compare_offset',float(value))


def render_reference_guide(ui,model_a,model_b,element,offset,tolerance):
    import streamlit as st
    a_hours,b_hours=typical_hours(model_a,element),typical_hours(model_b,element)
    rows=cycle_matches(a_hours,b_hours,offset,tolerance)
    compatible=[row for row in rows if row['compatible']]
    if not compatible:
        st.warning('The typical run schedules do not align with this offset and reference tolerance. '
                   'Open “Choosing a Model B offset” for a compatible example. Actual archive times can differ.')
    elif len(compatible)<len(rows):
        missing=', '.join(f'{row["a_hour"]:02d}Z' for row in rows if not row['compatible'])
        st.caption(f'Typical schedules align for {len(compatible)} of {len(rows)} A cycle hours. A hours without a nominal B match: {missing}. '
                   'Actual archive coverage determines the final matches.')
    with ui.expander('Choosing a Model B offset',expanded=False):
        st.write('The offset answers: which Model B run should be compared with each Model A run? '
                 'B target reference = A reference + offset. Negative selects an earlier target; positive selects a later target. '
                 'Both forecasts still verify the same station, valid time/date, and observation window.')
        st.caption(f'Typical {model_a.upper()} hours: '+', '.join(f'{h:02d}Z' for h in a_hours)
                   +f'. Typical {model_b.upper()} hours: '+', '.join(f'{h:02d}Z' for h in b_hours)
                   +'. These are schedule examples, not a check that a run exists in the selected archive.')
        if (model_a=='nbm' or model_b=='nbm') and element in QMD_NBM_ELEMENTS:
            st.caption('This NBM element uses QMD source initialization hours; NBM wind/gust use 01, 07, 13, 19Z. NBM MinRH uses 00/12Z.')
        a_hour=ui.selectbox('Example Model A hour (UTC)',a_hours,format_func=lambda hour:f'{hour:02d}Z',
                            key=f'offset_example_a_{model_a}_{model_b}_{element}')
        row=next(row for row in rows if row['a_hour']==a_hour)
        st.write(f'With A at {a_hour:02d}Z and offset {offset:+g} h, the closest typical B run is '
                 f'{cycle_label(row["b_hour"],row["b_day"])}: actual offset {row["actual_offset"]:+g} h, '
                 f'{abs(row["error"]):g} h from the requested B target. '
                 +('It is within the current reference tolerance.' if row['compatible'] else 'It is outside the current reference tolerance.'))
        presets=earlier_offsets(a_hour,b_hours)
        chosen=ui.selectbox('Same-time or earlier B run example',presets,
            format_func=lambda value:f'{cycle_label((a_hour+value)%24,(a_hour+value)//24)} ({value:+g} h)',
            key=f'offset_example_b_{model_a}_{model_b}_{element}_{a_hour}')
        ui.button('Use this offset',on_click=apply_offset,args=(chosen,),key='compare_apply_offset_example')
        st.caption('This button updates only the offset controls; it does not run verification. '
                   'One fixed offset applies to every A run. An example that fits one A hour may not fit all A hours.')
        st.write('For NDFD A at 00Z or 12Z: NBM wind at the previous 19Z or same-day 07Z uses −5 h; '
                 'NBMQMD at the previous 18Z or same-day 06Z uses −6 h. '
                 'With offset 0 and tolerance ±1 h, NBM 01Z can match NDFD 00Z; choose an explicit earlier offset if that is your intent.')
        st.caption('Reference tolerance allows a run near the requested B initialization; observation tolerance allows an observation near a valid time/window endpoint. '
                   'They serve different purposes. For a shared valid time, an earlier B run has a longer lead (B lead = A lead − actual offset). '
                   'Compatible hours cannot overcome missing archive files, sites, leads, valid targets, or observation windows.')
