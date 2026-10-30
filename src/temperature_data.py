"""Provenance-preserving observations for point-in-time market research."""

from urllib.parse import urlparse

import numpy as np
import pandas as pd


TIME_FIELDS = ('published_at', 'fetched_at', 'completed_at', 'valid_until')
TEXT_FIELDS = ('indicator_id', 'unit', 'market_coverage', 'data_period',
               'source_url', 'version')
COLUMNS = (*TEXT_FIELDS, 'value', 'revision', *TIME_FIELDS)
IDENTITY = ('indicator_id', 'data_period', 'published_at', 'source_url', 'version')


def _aware_timestamp(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError('Observation times and cutoff must include a timezone')
    return timestamp.tz_convert('UTC')


def validate_observations(frame: pd.DataFrame) -> pd.DataFrame:
    """Reject ambiguous contracts; duplicate fetches keep the earliest receipt."""
    if frame.empty:
        return pd.DataFrame(columns=COLUMNS)
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing observation fields: {sorted(missing)}')
    result = frame.copy()
    for field in TEXT_FIELDS:
        if not result[field].map(lambda x: isinstance(x, str) and bool(x.strip())).all():
            raise ValueError(f'Empty or invalid {field}')
        result[field] = result[field].str.strip()
    for source in result['source_url']:
        parsed = urlparse(source)
        if parsed.scheme not in ('https', 'http') or not parsed.netloc:
            raise ValueError('source_url must identify the source page')
    result['value'] = pd.to_numeric(result['value'], errors='coerce')
    if not np.isfinite(result['value']).all():
        raise ValueError('Observation value must be finite')
    if not result['revision'].map(lambda x: isinstance(x, (bool, np.bool_))).all():
        raise ValueError('revision must be boolean')
    for field in TIME_FIELDS:
        result[field] = pd.to_datetime(result[field].map(_aware_timestamp), utc=True)
    if (result['valid_until'] <= result['published_at']).any():
        raise ValueError('valid_until must follow publication')
    if (result['fetched_at'] < result['published_at']).any():
        raise ValueError('A value cannot be fetched before publication')
    if (result.groupby('indicator_id')[['unit', 'market_coverage']]
            .nunique(dropna=False) > 1).any().any():
        raise ValueError('Different units or market coverage require distinct indicator IDs')
    contract_fields = [field for field in result.columns
                       if field not in (*IDENTITY, 'fetched_at')]
    if (result.groupby(list(IDENTITY), dropna=False)[contract_fields]
            .nunique(dropna=False) > 1).any().any():
        raise ValueError('Conflicting records for the same publication vintage')
    if (result.groupby(['indicator_id', 'data_period', 'published_at'])
            [['value', 'completed_at', 'valid_until']]
            .nunique(dropna=False) > 1).any().any():
        raise ValueError('Conflicting sources at the same publication time')
    return (result.sort_values('fetched_at', kind='stable')
            .drop_duplicates(list(IDENTITY)).reset_index(drop=True))


def known_vintages(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Resolve releases without treating dataset capture as a new revision.

    An expired capture may only yield to an identical, still-valid release
    from the same source already received by cutoff. Changed values, genuine
    revisions and future receipts retain the expired latest-vintage behavior.
    """
    cutoff = _aware_timestamp(cutoff)
    result = validate_observations(frame)
    if result.empty:
        return result
    known = result[(result['published_at'] <= cutoff) &
                   (result['completed_at'] <= cutoff)]
    latest = (known.sort_values('published_at', kind='stable')
              .drop_duplicates(['indicator_id', 'data_period'], keep='last').copy())
    if 'publication_basis' not in known:
        return latest.reset_index(drop=True)
    candidates = latest[latest['publication_basis'].eq('captured_dataset') &
                        (latest['valid_until'] <= cutoff) & ~latest['revision']]
    # Build a release index once instead of scanning the full history for
    # every expired capture. Keep publication, receipt and expiry gates exact.
    from bisect import bisect_left
    eligible = known[~known['revision'] &
                     ~known['publication_basis'].eq('captured_dataset') &
                     (known['fetched_at'] <= cutoff) &
                     (known['valid_until'] > cutoff)].sort_values('published_at', kind='stable')
    releases = {}
    keys = ('indicator_id', 'data_period', 'source_url', 'value')
    for record in eligible.to_dict('records'):
        key = tuple(record[field] for field in keys)
        timestamps, records = releases.setdefault(key, ([], []))
        timestamps.append(record['published_at'])
        records.append(record)
    resolved = latest.to_dict('records')
    candidate_indices = set(candidates.index)
    for position, (index, capture) in enumerate(zip(latest.index, resolved)):
        if index not in candidate_indices:
            continue
        entry = releases.get(tuple(capture[field] for field in keys))
        if entry:
            timestamps, records = entry
            prior = bisect_left(timestamps, capture['published_at']) - 1
            if prior >= 0:
                resolved[position] = records[prior]
    latest = pd.DataFrame(resolved, columns=latest.columns)
    return latest.reset_index(drop=True)


def observations_at(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Latest published vintage per data period, as known at the research cutoff.

    Receipt time is not publication time: today's fetch may describe a historical
    release only when its original publication provenance is independently known.
    Expiration is exclusive and checked after selecting the latest known vintage.
    """
    cutoff = _aware_timestamp(cutoff)
    result = known_vintages(frame, cutoff)
    if result.empty:
        return result
    return result[result['valid_until'] > cutoff].reset_index(drop=True)
