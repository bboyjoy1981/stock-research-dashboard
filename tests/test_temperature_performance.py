from time import perf_counter
import pandas as pd
from src.temperature_data import known_vintages


def test_latest_cutoff_reuses_minute_but_respects_data_events():
    from src.market_temperature import _latest_cutoff
    frame = pd.DataFrame({'valid_until': [pd.Timestamp('2026-10-09T02:30:25Z')]})
    assert _latest_cutoff({}, frame, pd.Timestamp('2026-10-09T02:30:10Z')) == pd.Timestamp('2026-10-09T02:30Z')
    assert _latest_cutoff({}, frame, pd.Timestamp('2026-10-09T02:30:20Z')) == pd.Timestamp('2026-10-09T02:30Z')
    assert _latest_cutoff({}, frame, pd.Timestamp('2026-10-09T02:30:30Z')) == pd.Timestamp('2026-10-09T02:30:25Z')
    for key in ('published_at', 'completed_at', 'fetched_at'):
        event = pd.DataFrame({key: [pd.Timestamp('2026-10-09T02:30:28Z')]})
        assert _latest_cutoff({}, event, pd.Timestamp('2026-10-09T02:30:30Z')) == pd.Timestamp('2026-10-09T02:30:28Z')
    explicit = '2026-10-09T02:30:17Z'
    assert _latest_cutoff({'temperature_latest_cutoff': explicit}, frame) == pd.Timestamp(explicit)


def test_many_expired_captures_keep_original_release_without_quadratic_scan():
    rows = []
    for day in pd.date_range('2020-01-01', periods=1600):
        base = dict(indicator_id='sse', unit='points', market_coverage='沪市',
                    data_period=day.strftime('%Y-%m-%d'), source_url='https://example.com/history',
                    value=3000., revision=False, completed_at=day.tz_localize('UTC'))
        rows.append(dict(base, published_at=day.tz_localize('UTC'),
                         fetched_at=pd.Timestamp('2026-01-01T00:00Z'),
                         valid_until=pd.Timestamp('2030-01-01T00:00Z'), version='release',
                         publication_basis='original_release'))
        rows.append(dict(base, published_at=pd.Timestamp('2026-01-02T00:00Z'),
                         fetched_at=pd.Timestamp('2026-01-02T00:00Z'),
                         valid_until=pd.Timestamp('2026-01-03T00:00Z'), version='capture',
                         publication_basis='captured_dataset'))
    start = perf_counter()
    result = known_vintages(pd.DataFrame(rows), pd.Timestamp('2026-01-04T00:00Z'))
    elapsed = perf_counter() - start
    assert len(result) == 1600
    assert result['version'].eq('release').all()
    assert elapsed < 1.5, f'Historical resolution took {elapsed:.2f}s'
