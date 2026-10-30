import pandas as pd
import pytest

from src.temperature_history import parse_history_csv, parse_bis_japan


def test_cpi_yearly_change_does_not_fill_missing_months():
    dates = pd.date_range('2024-01-01', periods=14, freq='MS')
    text = 'observation_date,CPIAUCNS\n' + '\n'.join(
        f'{date:%Y-%m-%d},{value}' for date, value in zip(dates, [100,100]+[100]*10+[103.4,'']))
    frame = parse_history_csv(text, 'us_cpi_yoy', '2026-10-06T06:00:00Z')
    assert frame['value'].tolist() == [3.4]
    assert frame['data_period'].tolist() == ['2025-01']
    assert frame.iloc[0]['published_at'] == pd.Timestamp('2026-10-06T06:00:00Z')


def test_policy_month_end_excludes_current_incomplete_month():
    text = 'observation_date,DFEDTARU\n2026-09-29,4\n2026-09-30,4\n2026-10-01,4\n'
    frame = parse_history_csv(text, 'us_policy_rate', '2026-10-06T06:00:00Z')
    assert frame['data_period'].tolist() == ['2026-09']
    assert frame['value'].tolist() == [4]


def test_gold_excludes_weekend_carried_prices():
    frame = parse_history_csv('date,close_usd_per_troy_oz\n2026-10-02,4140.52\n2026-10-03,4140.52\n',
                              'gold', '2026-10-06T06:00:00Z')
    assert frame['data_period'].tolist() == ['2026-10-02']


def test_history_rejects_duplicate_and_invalid_values():
    with pytest.raises(ValueError):
        parse_history_csv('observation_date,DCOILBRENTEU\n2026-09-29,-1\n', 'oil', '2026-10-06T06:00:00Z')


def test_bis_japan_uses_only_reported_complete_months():
    text = 'FREQ,REF_AREA,COMPILATION,2026-07,2026-08,2026-09\nM,CN,LPR,3,3,3\nM,JP,BOJ short term policy rate,1,1,\n'
    frame = parse_bis_japan(text, '2026-10-06T06:00:00Z')
    assert frame['indicator_id'].unique().tolist() == ['jp_policy_rate']
    assert frame['data_period'].tolist() == ['2026-07','2026-08']
