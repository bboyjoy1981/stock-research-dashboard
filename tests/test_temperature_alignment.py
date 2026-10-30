import pandas as pd
from test_temperature_data import row


def records(key, dates):
    return [dict(row(), indicator_id=key, data_period=date, value=2,
                 published_at='2026-10-06T00:00:00Z', fetched_at='2026-10-06T00:00:00Z',
                 valid_until='2026-10-08T00:00:00Z') for date in dates]


def test_alignment_uses_real_common_dates_not_fill_or_latest_mixed_dates():
    from src.temperature_alignment import align_macro_history
    frame = pd.DataFrame(records('gold', ['2026-09-28', '2026-09-29', '2026-10-02']) +
                         records('oil', ['2026-09-28', '2026-09-29']) +
                         records('us_pmi', ['2026-09']))
    aligned, audit = align_macro_history(frame, '2026-10-07T00:00:00Z')
    assert aligned[aligned.indicator_id.eq('gold')].data_period.tolist() == ['2026-09-28', '2026-09-29']
    assert aligned[aligned.indicator_id.eq('us_pmi')].data_period.tolist() == ['2026-09']
    assert audit[0]['共同数据期'] == '2026-09-29'
    assert audit[0]['指标各自最新期'] == 'gold:2026-10-02 / oil:2026-09-29'


def test_no_overlap_preserves_missing_condition_without_forward_filling():
    from src.temperature_alignment import align_macro_history
    frame = pd.DataFrame(records('gold', ['2026-10-02']) + records('oil', ['2026-09-29']))
    aligned, audit = align_macro_history(frame, '2026-10-07T00:00:00Z')
    assert len(aligned) == 2
    assert audit[0]['共同数据期'] == '无共同有效期；不对齐'


def test_expired_records_cannot_supply_a_common_period():
    from src.temperature_alignment import align_macro_history
    frame = pd.DataFrame(records('gold', ['2026-09-29']) + records('oil', ['2026-09-29']))
    frame.loc[frame.indicator_id.eq('oil'), 'valid_until'] = '2026-10-06T12:00:00Z'
    aligned, audit = align_macro_history(frame, '2026-10-07T00:00:00Z')
    assert audit[0]['共同数据期'] == '无共同有效期；不对齐'
