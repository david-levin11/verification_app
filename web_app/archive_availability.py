"""Preflight date coverage from Parquet footers; never load full archives on startup."""
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re
import pandas as pd
import pyarrow.parquet as pq
import streamlit as st
from config import (get_element_config, get_percentile_columns, is_probabilistic,
                    get_model_pair_date_column, get_obs_filter_time_column, get_pairing_method)
from forecast_archive import refs_archive_root
from forecast_targets import NBM_MODELS
from page_controls import set_page_value


@dataclass
class Coverage:
    model: str
    element: str
    spans: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    unknown: bool = False
    first_init: object = None
    last_init: object = None

    @property
    def label(self):
        return ('Observations' if self.model=='obs' else self.model.upper())+' '+get_element_config(self.element)['label']


def naive(value):
    return pd.to_datetime(value, utc=True).tz_convert(None)


@lru_cache(maxsize=4096)
def footer(path, size, modified_ns):
    with pq.ParquetFile(path) as parquet:
        names=parquet.schema_arrow.names
        result={}
        for col in ['valid_time','init_time','ensemble_init_time','date','end_time','window_end']:
            if col not in names:continue
            low=[];high=[];complete=True
            for index in range(parquet.metadata.num_row_groups):
                stats=parquet.metadata.row_group(index).column(names.index(col)).statistics
                if stats is None or not stats.has_min_max:complete=False;break
                low.append(naive(stats.min));high.append(naive(stats.max))
            if complete and low:result[col]=(min(low),max(high))
        return names,result,parquet.metadata.num_rows


def coverage(root, model, element, refs_root=None):
    result=Coverage(model,element)
    obs=model in ['obs','urma'];cfg=get_element_config(element)
    sources=['wind'] if model=='refs' and element=='gust' else [element,'wind'] if element=='gust' else [element]
    by_month={}
    for source in sources:
        folder=refs_archive_root(root,refs_root)/source if model=='refs' else Path(root)/model/source
        for path in sorted(folder.glob('*.parquet')):
            match=re.fullmatch(r'(\d{4}_\d{2})(?:_'+re.escape(model)+'_'+re.escape(source)+r')?_archive\.parquet',path.name)
            if not match:continue
            month=match[1]
            if month in by_month:continue
            try:
                stat=path.stat();names,stats,rows=footer(str(path),stat.st_size,stat.st_mtime_ns)
                if not rows:continue
                expected=(cfg['obs_value_candidates'] if obs else
                          list(get_percentile_columns(element).values()) if is_probabilistic(model,element) else cfg['model_value_candidates'])
                if model=='refs':expected=expected+['p5','p50','p95']
                if not any(col in names for col in expected):
                    fields=[c for c in ['maxt','mint','minrh','rh','wind_speed_kt','precip6hr','precip24hr'] if c in names]
                    result.issues.append(f'{path.name} does not contain {cfg["label"].lower()} values'+
                                         (f' (contains {", ".join(fields)})' if fields else '')+'.')
                    continue
                timecol=get_obs_filter_time_column(element) if obs else get_model_pair_date_column(element) if get_pairing_method(element)=='date' else 'valid_time'
                if timecol not in names:
                    result.issues.append(f'{path.name} is missing its verification dates.');continue
                if timecol in stats:
                    low,high=stats[timecol]
                    if not obs and element=='maxt' and model in NBM_MODELS:
                        low=low-pd.Timedelta(days=1) if low.hour==6 else low
                        high=high-pd.Timedelta(days=1) if high.hour==6 else high
                else:
                    period=pd.Period(month.replace('_','-'),freq='M')
                    low,high=period.start_time,period.end_time
                    result.unknown=True
                by_month[month]=(low.normalize(),high.normalize())
                init=stats.get('ensemble_init_time' if model=='refs' else 'init_time')
                if init:
                    # The latest source month supplies a sensible first run for Storm Zoom.
                    result.first_init=init[0]
                    result.last_init=init[1]
            except Exception:
                result.issues.append(f'{path.name} could not be checked. Ask the archive administrator to check this file.')
                # Unreadable files cannot establish usable date coverage.
    result.spans=sorted(by_month.values())
    return result


def latest_dates(sources):
    common=None
    present=[source for source in sources if source.spans]
    for source in present:
        intervals=source.spans
        if common is None:common=list(intervals)
        else:common=[(max(a,c),min(b,d)) for a,b in common for c,d in intervals if max(a,c)<=min(b,d)]
    if not common:
        if not present:return fallback_dates()
        common=list(present[0].spans)
    end=max(b for a,b in common)
    month_start=end.replace(day=1)
    start=min(max(a,month_start) for a,b in common if b>=month_start)
    return start.date(),end.date()


def fallback_dates():
    end=pd.Timestamp.now(tz='UTC').tz_localize(None).normalize().replace(day=1)-pd.Timedelta(days=1)
    return end.replace(day=1).date(),end.date()


def seed_dates(page, keys, defaults, signature):
    """Refresh untouched defaults when sources change; retain user-selected dates."""
    state_key=f'_archive_date_defaults_{page}'
    previous=st.session_state.get(state_key,{})
    saved=st.session_state.get(f'_page_settings_{page}',{})
    for key,value in zip(keys,defaults):
        current=st.session_state.get(key,saved.get(key))
        if current is not None and previous.get('signature')!=signature and current==previous.get(key):
            set_page_value(page,key,value)
    st.session_state[state_key]={'signature':signature,**dict(zip(keys,defaults))}


def missing_ranges(source,start,end):
    cursor=pd.Timestamp(start).normalize();finish=pd.Timestamp(end).normalize();missing=[]
    for low,high in source.spans:
        if high<cursor:continue
        if low>finish:break
        if low>cursor:missing.append((cursor,min(finish,low-pd.Timedelta(days=1))))
        cursor=max(cursor,high+pd.Timedelta(days=1))
        if cursor>finish:break
    if cursor<=finish:missing.append((cursor,finish))
    return missing


def preflight(sources,start,end,container=None):
    ui=container or st
    if start is None or end is None:
        ui.error('Choose both a start date and an end date.');return False
    if start>end:
        ui.error('Start date must be on or before end date.');return False
    allowed=True
    for source in sources:
        overlap=any(low<=pd.Timestamp(end) and high>=pd.Timestamp(start) for low,high in source.spans)
        if not source.spans:
            ui.warning(f'No usable {source.label} archive was found. Choose another model or element, or ask the archive administrator to add the data.')
            allowed=False
        elif not overlap:
            low=min(a for a,b in source.spans).date();high=max(b for a,b in source.spans).date()
            ui.warning(f'No {source.label} data for your selected dates. Available dates: {low:%b %d, %Y}–{high:%b %d, %Y}. Choose dates inside that range.')
            allowed=False
        else:
            missing=missing_ranges(source,start,end)
            if missing:
                ranges='; '.join(f'{a:%b %d, %Y}–{b:%b %d, %Y}' for a,b in missing[:4])
                ui.warning(f'{source.label}: part of your date range has no archive coverage ({ranges}'+
                           ('; additional gaps' if len(missing)>4 else '')+'). Results will use only available data.')
        if source.spans:
            ui.caption(f'{source.label}: '+f'{min(a for a,b in source.spans):%b %d, %Y}–{max(b for a,b in source.spans):%b %d, %Y} UTC.')
        if source.issues:ui.warning(source.label+': '+' '.join(source.issues[:3]))
        if source.unknown:ui.caption('Some exact dates are unavailable in the archive metadata; the month is shown as an estimate.')
    if allowed:
        common=[(pd.Timestamp(start),pd.Timestamp(end))]
        for source in sources:
            common=[(max(a,c),min(b,d)) for a,b in common for c,d in source.spans if max(a,c)<=min(b,d)]
        if not common:
            ui.warning('The selected forecasts and observations have no overlapping archive dates. Choose a different date range or model combination.')
            allowed=False
    ui.caption('Archive date coverage does not guarantee every station, forecast hour, run, or observation is available. Matching checks those when you run verification.')
    return allowed
