"""Resolve Synoptic NDBC-prefixed IDs used for the same physical station."""

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
