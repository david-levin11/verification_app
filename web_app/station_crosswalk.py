"""Resolve Synoptic NDBC-prefixed IDs used for the same physical station."""

import pandas as pd

PREFIX = 'NDBC'


def archive_station_ids(stations):
    """Look up both forms, including aliases missing from station metadata."""
    ids = list(stations)
    for station in stations:
        if station.startswith(PREFIX):
            if bare_id := station.removeprefix(PREFIX):
                ids.append(bare_id)
        else:
            ids.append(PREFIX + station)
    return list(dict.fromkeys(ids))


def station_ids_in(frame):
    column = 'station_id' if 'station_id' in frame else 'stid'
    if column in frame:
        return set(frame[column].dropna().astype(str).str.strip().unique())
    return set()


def station_crosswalk(ids):
    """Map a bare ID to its prefixed ID when both are present."""
    return {
        bare_id: PREFIX + bare_id
        for bare_id in sorted(ids)
        if bare_id and not bare_id.startswith(PREFIX) and PREFIX + bare_id in ids
    }


def apply_station_crosswalk(frame, crosswalk, source_column):
    """Keep the source ID so matching can prefer the canonical ID on ties."""
    if not crosswalk or frame.empty:
        return frame
    frame = frame.rename(columns={'stid': 'station_id'}) if 'station_id' not in frame else frame.copy()
    frame[source_column] = frame['station_id'].astype('string').str.strip()
    frame['station_id'] = frame[source_column].map(crosswalk).fillna(frame[source_column])
    return frame


def prefer_canonical_station(frame, source_column):
    """Order the canonical row last for stable keep-last deduplication."""
    is_canonical = frame[source_column].eq(frame['station_id']).fillna(False)
    return frame.iloc[is_canonical.to_numpy(dtype=bool).argsort(kind='stable')]


def resolve_station_crosswalk(stations, *frames):
    """Find aliases for selected sites using metadata and available archive rows."""
    known_ids = set(stations).union(*(station_ids_in(frame) for frame in frames))
    return station_crosswalk(known_ids.intersection(archive_station_ids(stations)))


def canonical_station_ids(stations, crosswalk):
    return list(dict.fromkeys(crosswalk.get(station, station) for station in stations))


def canonical_station_metadata(metadata, crosswalk):
    metadata = apply_station_crosswalk(metadata, crosswalk, 'source_station_id')
    if 'source_station_id' in metadata:
        return prefer_canonical_station(metadata, 'source_station_id').drop_duplicates(
            'station_id', keep='last'
        )
    return metadata


def deduplicate_station_alias_rows(frame, keys, source_column):
    """Keep one row per key at aliased sites, retaining other stations' rows."""
    if source_column not in frame:
        return frame
    aliased_ids = frame.loc[frame[source_column].ne(frame.station_id), 'station_id']
    aliased = frame.station_id.isin(aliased_ids)
    if not aliased.any():
        return frame
    chosen = prefer_canonical_station(frame.loc[aliased], source_column)
    return pd.concat([frame.loc[~aliased], chosen.drop_duplicates(keys, keep='last')])
