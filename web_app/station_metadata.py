"""Shared station metadata controls and sortable station context."""
import math
import pandas as pd


def normalize_station_metadata(frame):
    result = frame.copy()
    if 'station_id' not in result and 'stid' in result:
        result = result.rename(columns={'stid': 'station_id'})
    if 'station_id' in result:
        result['station_id'] = result.station_id.astype('string').str.strip()
    if 'mnet_id' in result:
        result['mnet_id'] = (result.mnet_id.astype('string').str.strip()
                             .str.replace(r'^(\d+)\.0$', r'\1', regex=True))
        result['mnet_id'] = result.mnet_id.replace('', pd.NA)
    if 'elevation_ft' in result:
        result['elevation_ft'] = pd.to_numeric(result.elevation_ft, errors='coerce').replace(
            [float('inf'), -float('inf')], float('nan'))
    return result


def filter_station_metadata(frame, networks=None, minimum=None, maximum=None,
                            include_unknown_elevation=False):
    result = normalize_station_metadata(frame)
    if networks and 'mnet_id' in result:
        result = result[result.mnet_id.isin(networks)]
    if minimum is not None or maximum is not None:
        elevation = result.get('elevation_ft', pd.Series(float('nan'), index=result.index))
        keep = elevation.notna()
        if minimum is not None:
            keep &= elevation.ge(minimum)
        if maximum is not None:
            keep &= elevation.le(maximum)
        if include_unknown_elevation:
            keep |= elevation.isna()
        result = result[keep]
    return result


def network_elevation_controls(frame, ui, prefix):
    """No active filters means every station is retained, including unknowns."""
    frame = normalize_station_metadata(frame)
    networks = []
    if 'mnet_id' in frame:
        options = sorted(frame.mnet_id.dropna().unique().tolist(),
                         key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))
        networks = ui.multiselect('Synoptic Network ID', options, key=f'{prefix}_networks',
                                  help='Leave empty to include all networks, including stations with no network ID.')
    minimum = maximum = None
    unknown = False
    if 'elevation_ft' in frame:
        enabled = ui.checkbox('Filter by elevation', key=f'{prefix}_filter_elevation')
        if enabled:
            available = frame.elevation_ft.dropna()
            low = float(math.floor(available.min())) if not available.empty else 0.
            high = float(math.ceil(available.max())) if not available.empty else 10000.
            left, right = ui.columns(2)
            minimum = left.number_input('Minimum elevation (ft)', value=low, step=100., key=f'{prefix}_elevation_min')
            maximum = right.number_input('Maximum elevation (ft)', value=high, step=100., key=f'{prefix}_elevation_max')
            unknown = ui.checkbox('Include stations with unknown elevation', value=False,
                                  key=f'{prefix}_unknown_elevation')
            if minimum > maximum:
                ui.error('Minimum elevation must not exceed maximum elevation.')
                return frame.iloc[:0]
    return filter_station_metadata(frame, networks, minimum, maximum, unknown)


def station_context_table(frame):
    """Keep numeric elevation for sorting in Streamlit tables."""
    columns = ['station_id', 'name', 'mnet_id', 'elevation_ft', 'wfo_best', 'station_context']
    table = normalize_station_metadata(frame)[[c for c in columns if c in frame]].copy()
    if 'mnet_id' in table:
        numeric = pd.to_numeric(table.mnet_id, errors='coerce')
        if numeric.notna().sum() == table.mnet_id.notna().sum():
            table['mnet_id'] = numeric.astype('Int64')
    return table.rename(columns={
        'mnet_id': 'Synoptic Network ID', 'elevation_ft': 'Elevation (ft)'})
