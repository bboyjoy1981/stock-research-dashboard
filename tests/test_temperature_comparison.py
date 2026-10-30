import pandas as pd
from test_temperature_data import row


def test_official_2015_account_reference_uses_a_share_column():
    from src.temperature_comparison import compare_2015_accounts
    result = compare_2015_accounts(2397300)
    assert abs(result['mean'] - 4005.60 * 10000 / 12) < 1
    assert result['peak'] == 7198600
    assert result['peak_period'] == '2015-04'
    assert -29 < result['difference_pct'] < -28
    assert result['label'] == '低于2015年月均，远低于开户峰值'


def test_accounts_separate_spring_peak_and_july_september_reference():
    from src.temperature_comparison import compare_2015_accounts
    result = compare_2015_accounts(2397300)
    assert abs(result['spring_mean'] - 7018266.6667) < 1
    assert abs(result['summer_mean'] - 2474366.6667) < 1
    assert -4 < result['summer_difference_pct'] < -3


def test_comparison_values_are_readable_without_losing_units():
    from src.temperature_comparison import format_comparison_value
    assert format_comparison_value(2600772602615, 'CNY') == '2.60万亿元'
    assert format_comparison_value(2397300, 'accounts') == '239.73万户'
    assert format_comparison_value(.0875, 'ratio') == '8.75%'
    assert format_comparison_value(3842.19, 'points') == '3,842.19点'


def test_account_capture_excludes_future_placeholder_zeros():
    from src.temperature_comparison import parse_account_reference
    result = parse_account_reference([dict(TERM='2026.08', A_ACCT='239.73', MDATE='202608'),
        dict(TERM='2026.09', A_ACCT='0.00', MDATE='202608'),
        dict(TERM='2026年合计', A_ACCT='2521.40', MDATE='202608')])
    assert result == {'2026-08': 2397300}


def test_comparison_excludes_current_from_benchmark_and_reports_dates():
    from src.temperature_comparison import compare_history
    records = [row(indicator_id='a_new_accounts', unit='accounts', market_coverage='沪市A股账户',
                   data_period=str(p), value=100) for p in pd.period_range('2024-09', periods=12, freq='M')]
    records.append(row(indicator_id='a_new_accounts', unit='accounts', market_coverage='沪市A股账户',
                       data_period='2025-09', value=200))
    result = compare_history(pd.DataFrame(records), pd.Timestamp('2026-10-01T12:00:00Z'),
                             'a_new_accounts', '2024-09', '2025-09', 12)
    assert result['label'] == '高于参考期常态'
    assert result['mean'] == 100
    assert result['difference_pct'] == 100
    assert result['count'] == 12
    assert result['end'] == '2025-08'


def test_missing_2015_history_does_not_compare_with_other_years():
    from src.temperature_comparison import compare_history
    result = compare_history(pd.DataFrame([row()]), pd.Timestamp('2026-10-01T12:00:00Z'),
                             'cn_pmi', '2015-01', '2015-12', 12)
    assert result['label'] == '暂不可比'
    assert result['count'] == 0


def test_expired_current_does_not_produce_comparison():
    from src.temperature_comparison import compare_history
    result = compare_history(pd.DataFrame([row()]), pd.Timestamp('2030-01-01T12:00:00Z'),
                             'cn_pmi', '2024-01', '2026-12', 12)
    assert result['label'] == '暂不可比'
    assert '有效' in result['reason']
