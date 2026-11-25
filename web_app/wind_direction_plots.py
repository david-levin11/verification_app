"""Plots for the observed/forecast sector matrix and signed sector errors."""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from wind_verification import COMPASS_SECTORS


def sector_heatmap(matrix, as_percent):
    total = matrix.sum(axis=1)
    percent = matrix.div(total.where(total.gt(0)), axis=0) * 100
    rows = []
    for i, observed in enumerate(COMPASS_SECTORS):
        for j, forecast in enumerate(COMPASS_SECTORS):
            count = int(matrix.loc[observed, forecast])
            share = percent.loc[observed, forecast]
            rows.append(dict(
                observed_sector=observed, forecast_sector=forecast, count=count,
                percent=None if np.isnan(share) else float(share),
                sectors_apart=min(abs(i-j), 8-abs(i-j)),
                label=('' if not count else f'{share:.0f}%' if as_percent else f'{count:,}'),
            ))

    x = {'field': 'forecast_sector', 'type': 'ordinal', 'sort': list(COMPASS_SECTORS),
         'title': 'Forecast sector', 'axis': {'labelAngle': 0}}
    y = {'field': 'observed_sector', 'type': 'ordinal', 'sort': list(COMPASS_SECTORS),
         'title': 'Observed sector'}
    field = 'percent' if as_percent else 'count'
    scale = {'scheme': 'blues', 'domain': [0, 100 if as_percent else max(1, int(matrix.max().max()))]}
    title = '% within observed sector' if as_percent else 'Pairs'
    return {
        'data': {'values': rows}, 'height': 315,
        'encoding': {'x': x, 'y': y},
        'layer': [
            {'mark': {'type': 'rect', 'invalid': None, 'stroke': '#d3dae2', 'strokeWidth': 0.6},
             'params': [{'name': 'sector_pair', 'select': {'type': 'point',
                         'fields': ['observed_sector', 'forecast_sector'], 'toggle': False}}],
             'encoding': {
                 'color': {'condition': {'test': 'isValid(datum.percent)', 'field': field,
                           'type': 'quantitative', 'title': title, 'scale': scale},
                           'value': '#e5e7eb'},
                 'stroke': {'condition': {'param': 'sector_pair', 'empty': False, 'value': '#c67321'},
                            'value': '#d3dae2'},
                 'strokeWidth': {'condition': {'param': 'sector_pair', 'empty': False, 'value': 2},
                                 'value': 0.6},
                 'tooltip': [
                     {'field': 'observed_sector', 'title': 'Observed'},
                     {'field': 'forecast_sector', 'title': 'Forecast'},
                     {'field': 'count', 'title': 'Pairs', 'format': ','},
                     {'field': 'percent', 'title': '% within observed sector', 'format': '.1f'},
                     {'field': 'sectors_apart', 'title': 'Sectors apart'},
                 ],
             }},
            {'mark': {'type': 'text', 'fontWeight': 600},
             'encoding': {'text': {'field': 'label'},
                          'color': {'condition': {'test': f'datum.{field} > {scale["domain"][1] * .6}',
                                                  'value': 'white'}, 'value': '#162b42'}}},
        ],
    }


def sector_error_rose(sector_errors):
    offsets = np.array([0, 1, 2, 3, 4, -3, -2, -1])
    positions = offsets * np.pi / 4
    shares = sector_errors.reindex(offsets).to_numpy() / sector_errors.sum()
    fig, ax = plt.subplots(figsize=(4.6, 3.7), layout='constrained', subplot_kw={'projection': 'polar'})
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    colors = ['#23766e' if offset == 0 else '#557996' if abs(offset) == 1
              else '#a24725' if offset == 4 else '#cd772e' for offset in offsets]
    ax.bar(positions, shares, width=np.pi * .19, color=colors)
    ax.set_xticks(positions, ['Same', '+1', '+2', '+3', 'Opposite', '−3', '−2', '−1'])
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_rlabel_position(72)
    ax.set_axisbelow(True)
    return fig
