"""Displays for paired model comparison scores."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from comparison import model_view, METRIC_LABELS
from probability import probability_cases, reliability_table


def plot_group_scores(table, group, metric, label_a, label_b, xlabel):
    # Retain groups with undefined scores so missing denominators are visible,
    # and one model's undefined FAR does not hide the other model's valid score.
    data=table[table.metric.eq(metric)]
    fig,ax=plt.subplots(figsize=(10,4))
    positions=np.arange(len(data))
    ax.plot(positions,data.a,'o-',label=label_a,color='#2166ac')
    ax.plot(positions,data.b,'s-',label=label_b,color='#b35806')
    ax.set_xticks(positions, [str(v) for v in data[group]])
    if len(data) > 5:
        plt.setp(ax.get_xticklabels(), rotation=35, ha='right')
    for position, (_, row) in zip(positions, data.iterrows()):
        if pd.isna(row.a) and pd.isna(row.b):
            ax.text(position, .03, 'N/A', transform=ax.get_xaxis_transform(),
                    ha='center', va='bottom', fontsize=8, color='#666666')
    ax.set_ylabel(METRIC_LABELS.get(metric,metric));ax.set_xlabel(xlabel)
    ax.grid(alpha=.25);ax.legend();fig.tight_layout()
    return fig


def plot_probability_comparison(cases, element, threshold, operator, label_a, label_b,
                                probability_a, probability_b):
    a=probability_cases(model_view(cases,'a'),element,threshold,operator) if probability_a else None
    b=probability_cases(model_view(cases,'b'),element,threshold,operator) if probability_b else None
    if a is not None and b is not None:
        shared=a.index.intersection(b.index);a=a.loc[shared];b=b.loc[shared]
    fig,(ax,counts)=plt.subplots(2,1,figsize=(8,7),height_ratios=[3,1])
    ax.plot([0,1],[0,1],'k--',label='Perfect reliability')
    for data,label,color in [(a,label_a,'#2166ac'),(b,label_b,'#b35806')]:
        if data is None or data.empty:
            continue
        table=reliability_table(data)
        ax.plot(table.mean_forecast,table.observed_freq,'o-',label=label,color=color)
        counts.plot([interval.mid for interval in table.prob_bin],table['count'],'o-',color=color,label=label)
    ax.set(xlim=(0,1),ylim=(0,1),xlabel='Forecast probability',ylabel='Observed event frequency',
           title=f'{element} {operator} {threshold}')
    ax.legend();ax.grid(alpha=.25)
    counts.set(xlim=(0,1),xlabel='Forecast probability bin',ylabel='Cases');counts.grid(alpha=.25)
    fig.tight_layout();return fig


def station_map_view(data):
    """Fit a 900 x 500 map, using the short longitude arc across the dateline."""
    import pydeck as pdk
    angles = np.sort(np.mod(data.longitude.to_numpy(), 360))
    gaps = np.diff(np.r_[angles, angles[0] + 360])
    start = angles[(int(np.argmax(gaps)) + 1) % len(angles)]
    longitudes = start + np.mod(data.longitude.to_numpy() - start, 360)
    center = (longitudes.min() + longitudes.max()) / 2
    longitude = (center + 180) % 360 - 180
    # Keep Aleutian points on the same rendered world copy as the map center.
    data['map_longitude'] = longitudes + longitude - center
    y = np.log(np.tan(np.pi / 4 + np.radians(data.latitude.to_numpy()) / 2))
    latitude = np.degrees(2 * np.arctan(np.exp((y.min() + y.max()) / 2)) - np.pi / 2)
    x_span = max(float(np.ptp(longitudes)) / 360, 1e-6)
    y_span = max(float(np.ptp(y)) / (2 * np.pi), 1e-6)
    zoom = min(np.log2(780 / (512 * x_span)), np.log2(380 / (512 * y_span)))
    return pdk.ViewState(latitude=float(latitude), longitude=float(longitude),
                         zoom=float(np.clip(zoom, 1, 9)))


def station_difference_map(table, metadata, metric, label_a, label_b, minimum_cases=1):
    """Positive advantage consistently means A performs better."""
    import pydeck as pdk
    if metadata.empty or not {'station_id','latitude','longitude'}.issubset(metadata):
        return None, pd.DataFrame()
    data=table[table.metric.eq(metric) & table.n.ge(minimum_cases)].copy()
    if data.empty:
        return None,data
    from comparison import HIGHER_BETTER
    data['advantage']=data.a-data.b if metric in HIGHER_BETTER else data.b-data.a
    if metric=='bias':
        data['advantage']=data.b.abs()-data.a.abs()
    if metric=='frequency_bias':
        data['advantage']=(data.b-1).abs()-(data.a-1).abs()
    data=data.merge(metadata.drop_duplicates('station_id'),on='station_id',how='left')
    for col in ['latitude','longitude']:
        data[col]=pd.to_numeric(data[col],errors='coerce')
    data=data.dropna(subset=['latitude','longitude','advantage'])
    data=data[data.latitude.between(-85,85) & data.longitude.between(-180,180)].copy()
    if data.empty:
        return None,data
    span=max(float(data.advantage.abs().max()),1e-12)
    def color(value):
        strength=min(abs(value)/span,1)
        target=np.array([33,102,172] if value>0 else [179,88,6])
        return [*np.round(245+(target-245)*strength).astype(int).tolist(),210]
    data['color']=data.advantage.apply(color)
    data['point_radius']=4 + pd.to_numeric(data.n,errors='coerce').fillna(0).rank(pct=True) * 5
    view=station_map_view(data)
    layer=pdk.Layer('ScatterplotLayer',data=data,get_position='[map_longitude, latitude]',
                    get_fill_color='color',get_radius='point_radius',radius_units='"pixels"',
                    stroked=True,get_line_color=[60,60,60,170],line_width_units='"pixels"',
                    get_line_width=1,pickable=True)
    context = ('Network ID: {mnet_id}<br>' if 'mnet_id' in data else '')
    context += ('Elevation: {elevation_ft} ft<br>' if 'elevation_ft' in data else '')
    deck=pdk.Deck(layers=[layer],initial_view_state=view,
        map_style='light',tooltip={'html':f'<b>{{station_id}}</b><br>{context}{label_a}: {{a}}<br>{label_b}: {{b}}<br>Cases: {{n}}<br>Advantage for A: {{advantage}}'})
    return deck,data
