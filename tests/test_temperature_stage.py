import pandas as pd
import pytest
from test_temperature_data import row
from src.temperature_stage import evaluate_trend_stage


def fixture(values):
    dates = pd.bdate_range('2024-01-02', periods=len(values))
    records = []
    for key in ('sse','szse','chinext','star50','csi300'):
        for date, value in zip(dates, values):
            stamp = date.tz_localize('Asia/Shanghai') + pd.Timedelta(hours=15)
            records.append(row(indicator_id=key, unit='points', value=value,
                               data_period=f'{date:%Y-%m-%d}', published_at=stamp,
                               completed_at=stamp, fetched_at=stamp, valid_until='2030-01-01T00:00:00Z'))
    return pd.DataFrame(records), stamp


def test_uptrend_and_cycle_drawdown_are_separate_from_temperature():
    frame, cutoff = fixture(list(range(3000,3300)))
    result = evaluate_trend_stage(frame, cutoff)
    assert result['label'] == '上升趋势'
    assert result['indices'][0]['cycle_drawdown'] == 0
    assert result['annual_line']['status'] == '年线上方'
    assert result['annual_line']['level'] == pytest.approx(3174.5)
    assert 'internal_score' not in result


def test_declining_indices_report_downtrend_not_bottom():
    frame, cutoff = fixture(list(range(5000,4700,-1)))
    assert evaluate_trend_stage(frame, cutoff)['label'] == '下行趋势'


def test_missing_history_never_uses_single_snapshot_for_trend():
    assert evaluate_trend_stage(pd.DataFrame(), pd.Timestamp('2026-09-30T15:00:00+08:00'))['label'] == '待补指数历史'


def test_future_price_does_not_change_cycle_peak():
    frame, cutoff = fixture(list(range(3000,3300)))
    future = frame.iloc[-1].to_dict()
    future.update(indicator_id='sse', value=99999, data_period='2026-09-30',
                  published_at=pd.Timestamp('2026-09-30T15:00:00+08:00'),
                  fetched_at=pd.Timestamp('2026-09-30T16:00:00+08:00'),
                  completed_at=pd.Timestamp('2026-09-30T15:00:00+08:00'))
    original = evaluate_trend_stage(frame, cutoff)
    updated = evaluate_trend_stage(pd.concat([frame,pd.DataFrame([future])]), cutoff)
    assert updated['indices'][0]['cycle_peak'] == original['indices'][0]['cycle_peak']


def test_annual_line_break_alone_does_not_confirm_downtrend():
    frame, cutoff = fixture(list(range(3800,4099)) + [3690])
    result = evaluate_trend_stage(frame, cutoff)
    assert result['annual_line']['status'] == '年线下方 · 趋势转弱'
    assert result['annual_line']['below_sessions'] == 1
    assert result['annual_line']['distance'] < 0


def test_five_closes_below_falling_annual_line_confirm_downtrend():
    frame, cutoff = fixture(list(range(5000,4700,-1)))
    result = evaluate_trend_stage(frame, cutoff)
    assert result['annual_line']['status'] == '下行趋势确认'
    assert result['annual_line']['below_sessions'] >= 5
