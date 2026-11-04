"""Consistent forecast percentile lines and shading for storm time series."""
import numpy as np


def draw_quantile_plume(ax,positions,values,valid,color='#003399',label=''):
    """Connect archived quantiles visually; missing/invalid rows break bands."""
    prefix=f'{label}: ' if label else ''
    for low,high,a,b,alpha in [(5,95,0,4,.12),(25,75,1,3,.30)]:
        lower=np.where(valid,values[:,a],np.nan)
        upper=np.where(valid,values[:,b],np.nan)
        if len(positions)==1:
            ax.vlines(positions[valid],lower[valid],upper[valid],color=color,
                      linewidth=8 if low==25 else 3,alpha=.6,label=f'{prefix}p{low}–p{high}')
        else:
            ax.fill_between(positions,lower,upper,color=color,alpha=alpha,label=f'{prefix}p{low}–p{high}')
            ax.plot(positions,lower,color=color,linewidth=.8,alpha=.7)
            ax.plot(positions,upper,color=color,linewidth=.8,alpha=.7)
    ax.plot(positions,np.where(valid,values[:,2],np.nan),color=color,linewidth=1.8,
            marker='o' if len(positions)==1 else None,label=f'{prefix}p50 median')
