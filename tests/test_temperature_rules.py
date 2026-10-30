import pandas as pd
import pytest

from src.temperature_rules import (
    aggregate_scores, compare_temperature, evaluate_temperature,
    percentile_rank, temperature_label,
)
from test_temperature_data import row


@pytest.mark.parametrize('score,label', [(0, '过冷'), (19.99, '过冷'),
    (20, '偏冷'), (40, '中性'), (60, '偏热'), (80, '过热'), (100, '过热')])
def test_temperature_boundary(score, label):
    assert temperature_label(score) == label


@pytest.mark.parametrize('score', [-1, 101, float('nan')])
def test_invalid_scores_have_no_label(score):
    assert temperature_label(score) == '暂无法判断'


def test_dated_policy_decision_is_valid_but_insufficient_history():
    frame = pd.DataFrame([row(indicator_id='cn_policy_rate', value=1.4,
                              unit='percent', data_period='2026-09-29')])
    result = evaluate_temperature(frame, pd.Timestamp('2026-09-30T15:00:00+08:00'))
    assert 'cn_policy_rate：数据期格式不符' not in result['metrics']['policy']['reason']
    assert result['metrics']['policy']['label'] == '待补数据'


def test_percentile_ties_and_minimum_history():
    assert percentile_rank(2, [1, 2, 2, 3], minimum=4) == 50
    assert percentile_rank(2, [1, 2, 3], minimum=4) is None
    assert percentile_rank(2, [1, 2, float('nan'), 3], minimum=4) is None


def scores():
    return dict(pmi=20, inflation=20, policy=20, commodities=20,
                us=60, japan=60, korea=60,
                sentiment=80, activity=80, a_indices=80, margin=80, accounts=80)


def test_fixed_three_group_weights():
    result = aggregate_scores(scores())
    assert result['internal_score'] == pytest.approx(67)
    assert result['coverage'] == 100
    assert result['label'] == '偏热'


def test_account_is_auxiliary_and_never_changes_temperature():
    inputs = scores()
    inputs.pop('accounts')
    result = aggregate_scores(inputs)
    assert result['coverage'] == 100
    assert result['internal_score'] == pytest.approx(67)
    assert result['missing'] == []


@pytest.mark.parametrize('missing', [('pmi',), ('margin',), ('japan', 'korea'),
                                       ('inflation', 'japan', 'margin'), ('japan', 'margin')])
def test_insufficient_group_or_total_coverage_does_not_grade(missing):
    inputs = scores()
    for key in missing:
        inputs.pop(key)
    result = aggregate_scores(inputs)
    assert result['internal_score'] is None
    assert result['label'] == '暂无法判断'


def test_null_not_treated_as_neutral():
    inputs = scores()
    inputs['sentiment'] = None
    result = aggregate_scores(inputs)
    assert result['coverage'] == 75
    assert result['internal_score'] is None


def monthly_series(indicator, values, unit='index', coverage='fixed'):
    records = []
    for period, value in zip(pd.period_range('2022-01', periods=len(values), freq='M'), values):
        publication = period.end_time.normalize().tz_localize('Asia/Shanghai') + pd.Timedelta(hours=9)
        records.append(row(indicator_id=indicator, value=value, unit=unit,
            market_coverage=coverage, data_period=str(period), published_at=publication,
            completed_at=publication, fetched_at=publication + pd.Timedelta(hours=1),
            valid_until=publication + pd.DateOffset(months=2)))
    return records


def test_monthly_pmi_needs_two_countries_and_excludes_current_from_history():
    records = monthly_series('cn_pmi', list(range(41))) + monthly_series('us_pmi', list(range(41)))
    result = evaluate_temperature(pd.DataFrame(records), pd.Timestamp('2025-05-31T15:00:00+08:00'))
    # Level at historical maximum=100; constant three-month change=50, average=75.
    assert result['metrics']['pmi']['score'] == 75
    assert result['coverage'] == 4.5
    assert result['internal_score'] is None
    audit = next(item for item in result['calculation_audit'] if item['calculation'] == '3个月变化')
    assert audit['history_start'] == '2022-04'
    assert audit['history_end'] == '2025-04'
    assert audit['current_period'] == '2025-05'


def test_incomplete_composite_not_partially_reweighted():
    result = evaluate_temperature(pd.DataFrame(monthly_series('cn_pmi', list(range(41)))),
                                  pd.Timestamp('2025-05-31T15:00:00+08:00'))
    assert result['coverage'] == 0
    assert result['metrics']['pmi']['score'] is None


def test_future_month_does_not_affect_scoring():
    records = monthly_series('cn_pmi', list(range(41))) + monthly_series('us_pmi', list(range(41)))
    original = evaluate_temperature(pd.DataFrame(records), pd.Timestamp('2025-05-31T15:00:00+08:00'))
    future = monthly_series('cn_pmi', list(range(41)) + [-900])[-1]
    updated = evaluate_temperature(pd.DataFrame(records + [future]), pd.Timestamp('2025-05-31T15:00:00+08:00'))
    assert updated['metrics']['pmi']['score'] == original['metrics']['pmi']['score']


def test_missing_historical_month_not_treated_as_three_month_change():
    records = monthly_series('cn_pmi', list(range(41))) + monthly_series('us_pmi', list(range(41)))
    records = [r for r in records if r['data_period'] != '2025-02']
    result = evaluate_temperature(pd.DataFrame(records), pd.Timestamp('2025-05-31T15:00:00+08:00'))
    assert result['metrics']['pmi']['score'] is None


def test_empty_data_returns_missing_groups_and_no_grade():
    result = evaluate_temperature(pd.DataFrame(), pd.Timestamp('2026-09-30T15:00:00+08:00'))
    assert result['label'] == '暂无法判断'
    assert result['coverage'] == 0
    assert len(result['missing']) == 11


def daily_series(indicator, values, unit='points'):
    records = []
    for day, value in zip(pd.bdate_range('2025-01-01', periods=len(values)), values):
        publication = day.tz_localize('Asia/Shanghai') + pd.Timedelta(hours=15)
        records.append(row(indicator_id=indicator, value=value, unit=unit,
            market_coverage='fixed adjusted universe', data_period=day.strftime('%Y-%m-%d'),
            published_at=publication, completed_at=publication,
            fetched_at=publication + pd.Timedelta(hours=1),
            valid_until=publication + pd.Timedelta(days=7)))
    return records


def test_index_trends_use_historical_returns_not_single_day_prices():
    records = daily_series('nikkei225', list(range(1, 201)))
    result = evaluate_temperature(pd.DataFrame(records), records[-1]['published_at'])
    assert result['metrics']['japan']['score'] == 0
    assert result['coverage'] == 4


def test_turnover_uses_level_and_twenty_session_relative_activity():
    records = daily_series('a_amount', list(range(1, 201)), unit='CNY')
    result = evaluate_temperature(pd.DataFrame(records), records[-1]['published_at'])
    assert result['metrics']['activity']['score'] == 50


def test_short_daily_history_not_scored():
    records = daily_series('nikkei225', list(range(1, 121)))
    result = evaluate_temperature(pd.DataFrame(records), records[-1]['published_at'])
    assert result['metrics']['japan']['score'] is None


def test_unit_mismatch_not_scored():
    records = daily_series('a_amount', list(range(1, 201)), unit='USD')
    result = evaluate_temperature(pd.DataFrame(records), records[-1]['published_at'])
    assert result['metrics']['activity']['score'] is None


def test_monthly_inflation_reverse_rank_and_complete_us_core():
    values = [x*x for x in range(41)]
    records = sum([monthly_series(key, values, unit='percent')
                   for key in ('cn_cpi_yoy', 'us_cpi_yoy', 'us_core_cpi_yoy')], [])
    result = evaluate_temperature(pd.DataFrame(records), records[-1]['published_at'])
    assert result['metrics']['inflation']['score'] == 0


def test_actual_sentiment_all_components_required_and_same_date():
    records = sum([daily_series(key, [x/200 for x in range(1, 151)], unit='ratio')
                   for key in ('a_breadth', 'a_newhigh_low_60', 'a_limit_balance')], [])
    result = evaluate_temperature(pd.DataFrame(records), records[-1]['published_at'])
    assert result['metrics']['sentiment']['score'] == 100
    missing_last = records[:-1]
    result = evaluate_temperature(pd.DataFrame(missing_last), records[-1]['published_at'])
    assert result['metrics']['sentiment']['score'] is None


def test_only_explicit_adjacent_calendar_days_can_confirm_stage():
    previous = aggregate_scores(scores())
    previous['trade_date'] = '2026-09-29'
    current = aggregate_scores(scores())
    current['trade_date'] = '2026-09-30'
    assert compare_temperature(current, previous, ['2026-09-29', '2026-09-30']) == {
        'direction': '持平', 'confirmed': True, 'stage_note': '连续交易日同档'}
    assert compare_temperature(current, previous, [])['confirmed'] is False


@pytest.mark.parametrize('change', ['gap', 'rule', 'coverage'])
def test_non_comparable_previous_day_does_not_show_direction(change):
    previous = aggregate_scores(scores())
    previous['trade_date'] = '2026-09-28' if change == 'gap' else '2026-09-29'
    if change == 'rule':
        previous['rule_version'] = 'old'
    if change == 'coverage':
        previous['missing'] = ['accounts']
    current = aggregate_scores(scores())
    current['trade_date'] = '2026-09-30'
    result = compare_temperature(current, previous, ['2026-09-28', '2026-09-29', '2026-09-30'])
    assert result['direction'] == '缺可比上日'
    assert result['confirmed'] is False


def test_equal_coverage_but_changed_universe_not_comparable():
    previous = aggregate_scores(scores())
    previous.update(trade_date='2026-09-29', input_signature='universe-A')
    current = aggregate_scores(scores())
    current.update(trade_date='2026-09-30', input_signature='universe-B')
    assert compare_temperature(current, previous, ['2026-09-29', '2026-09-30'])['direction'] == '缺可比上日'
def test_audit_preserves_computable_features_even_when_history_is_insufficient():
    records = daily_series('sp500', list(range(100, 170)))
    result = evaluate_temperature(pd.DataFrame(records), pd.Timestamp(records[-1]['published_at']))
    trace = [item for item in result['calculation_audit'] if item['indicator_id'] == 'sp500']
    assert len(trace) == 3
    five = next(item for item in trace if item['calculation'] == '5日涨跌幅')
    assert five['value'] == pytest.approx(169 / 164 - 1)
    assert five['history_count'] == 64
    assert five['percentile'] is None
    assert five['minimum'] == 120
    assert result['metrics']['us']['score'] is None
