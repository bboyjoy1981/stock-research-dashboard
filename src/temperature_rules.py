"""Experimental, point-in-time research rules; not a trading signal."""

import math
from urllib.parse import urlparse

import pandas as pd

from src.temperature_data import observations_at, validate_observations, known_vintages

RULE_VERSION = 'experimental-v2-15-20-65'
METRICS = {
    'pmi': ('宏观环境', '中美PMI', 4.5),
    'inflation': ('宏观环境', '中美通胀', 3),
    'policy': ('宏观环境', '央行政策', 4.5),
    'commodities': ('宏观环境', '黄金与原油', 3),
    'us': ('海外股市', '美国股市', 12),
    'japan': ('海外股市', '日本股市', 4),
    'korea': ('海外股市', '韩国股市', 4),
    'sentiment': ('A股热度', '市场情绪与上涨广度', 25),
    'activity': ('A股热度', '成交活跃度', 20),
    'a_indices': ('A股热度', '指数短中期强弱', 10),
    'margin': ('A股热度', '两融与参与度', 10),
}
GROUPS = {'宏观环境': (15, 12), '海外股市': (20, 16), 'A股热度': (65, 58.5)}


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def temperature_label(score):
    if not _finite(score) or not 0 <= score <= 100:
        return '暂无法判断'
    return ('过冷', '偏冷', '中性', '偏热', '过热')[min(int(score // 20), 4)]


def percentile_rank(value, history, minimum=120):
    """Midrank against prior finite observations, never including current."""
    values = [float(item) for item in history if _finite(item)]
    if not _finite(value) or len(values) < minimum:
        return None
    return 100 * (sum(item < value for item in values) +
                  .5 * sum(item == value for item in values)) / len(values)


def aggregate_scores(scores):
    """Internal aggregation only; public evaluator accepts raw observations."""
    valid = {key: float(value) for key, value in scores.items()
             if key in METRICS and _finite(value) and 0 <= value <= 100}
    groups = {}
    coverage = 0
    for name, (weight, threshold) in GROUPS.items():
        members = [key for key in valid if METRICS[key][0] == name]
        available = sum(METRICS[key][2] for key in members)
        score = (sum(valid[key] * METRICS[key][2] for key in members) / available
                 if available >= threshold else None)
        groups[name] = dict(weight=weight, available=available,
                            threshold=threshold, internal_score=score,
                            label=temperature_label(score))
        coverage += available
    enough = coverage >= 90 and all(g['internal_score'] is not None for g in groups.values())
    score = sum(g['internal_score'] * g['weight'] / 100 for g in groups.values()) if enough else None
    return dict(label=temperature_label(score), internal_score=score,
                coverage=coverage, missing=[key for key in METRICS if key not in valid],
                groups=groups, rule_version=RULE_VERSION,
                reasons=['部分指标缺失'] if enough and coverage < 100 else [])


def _known_history(observations, cutoff):
    # Old releases remain legitimate historical samples after their freshness
    # expires. Only the *current* input is required to be fresh at the cutoff.
    return known_vintages(observations, cutoff)


def _series(known, fresh, key, unit, monthly=False):
    records = known[known['indicator_id'] == key].copy()
    if records.empty:
        raise ValueError(f'{key}：缺原始数据')
    if not records['unit'].eq(unit).all():
        raise ValueError(f'{key}：单位不符，应为{unit}')
    expected_format = r'\d{4}-\d{2}' if monthly else r'\d{4}-\d{2}-\d{2}'
    if not records['data_period'].str.fullmatch(expected_format).all():
        raise ValueError(f'{key}：数据期格式不符')
    records = records.sort_values('data_period')
    last = records.iloc[-1]
    current = fresh[(fresh['indicator_id'] == key) & (fresh['data_period'] == last['data_period'])]
    if current.empty:
        raise ValueError(f'{key}：最新已知观测已过期')
    if monthly:
        index = pd.PeriodIndex(records['data_period'], freq='M')
        result = pd.Series(records['value'].to_numpy(), index=index)
        result = result.reindex(pd.period_range(index.min(), index.max(), freq='M'))
    else:
        index = pd.to_datetime(records['data_period'])
        result = pd.Series(records['value'].to_numpy(), index=index)
    return result, str(last['data_period']), last['market_coverage']


def _rank(feature, minimum, inverse=False):
    score = percentile_rank(feature.iloc[-1], feature.iloc[:-1], minimum)
    if score is None:
        raise ValueError(f'缺可比历史：需至少{minimum}个有效历史样本，不含当期')
    return 100 - score if inverse else score


def _mean(values):
    if any(value is None for value in values):
        raise ValueError('缺可比历史：核算明细列出各项有效样本数与最低要求')
    return sum(values) / len(values)


def evaluate_temperature(observations: pd.DataFrame, cutoff: pd.Timestamp) -> dict:
    cutoff = pd.Timestamp(cutoff)
    # observations_at validates timezone and provenance before any computation.
    fresh = observations_at(observations, cutoff)
    known = _known_history(observations, cutoff.tz_convert('UTC'))
    detail, scored, audit = {}, {}, []

    def load(key, unit, monthly=False):
        series, period, coverage = _series(known, fresh, key, unit, monthly)
        series.name = key
        return series, period, coverage

    def rank(feature, minimum, inverse=False, calculation='原始水平'):
        history = [float(value) for value in feature.iloc[:-1] if _finite(value)]
        historical = feature.iloc[:-1].dropna()
        historical = historical[historical.map(_finite)]
        def period_text(index):
            return str(index) if isinstance(index, pd.Period) else pd.Timestamp(index).strftime('%Y-%m-%d')
        value = float(feature.iloc[-1]) if _finite(feature.iloc[-1]) else None
        percentile = percentile_rank(value, history, minimum)
        score = (100 - percentile if inverse else percentile) if percentile is not None else None
        audit.append(dict(indicator_id=feature.name, calculation=calculation,
            value=value, history_count=len(history), minimum=minimum,
            history_start=period_text(historical.index[0]) if len(historical) else None,
            history_end=period_text(historical.index[-1]) if len(historical) else None,
            current_period=period_text(feature.index[-1]),
            percentile=percentile, inverse=inverse, label=temperature_label(score),
            reason='已核算；试验规则' if score is not None else '缺当前衍生值或可比历史样本'))
        return score

    def month_change(key, unit, inverse=False):
        series, period, _ = load(key, unit, True)
        return rank(series - series.shift(3), 36, inverse, '3个月变化'), period

    def pmi(key):
        series, period, _ = load(key, 'index', True)
        return _mean([rank(series, 36), rank(series - series.shift(3), 36, calculation='3个月变化')]), period

    def policy(key):
        periods = known.loc[known['indicator_id'].eq(key), 'data_period']
        monthly = periods.empty or periods.str.fullmatch(r'\d{4}-\d{2}').all()
        series, period, _ = load(key, 'percent', monthly)
        timestamps = series.index.to_timestamp(how='end').normalize() if monthly else series.index
        differences = []
        for timestamp, value in zip(timestamps, series):
            prior = series[timestamps <= timestamp - pd.Timedelta(days=90)]
            differences.append(value - prior.iloc[-1] if not prior.empty else float('nan'))
        return rank(pd.Series(differences, index=series.index, name=key), 36 if monthly else 120, True, '90日政策利率变化'), period

    def trend(key):
        series, period, _ = load(key, 'points')
        if (series <= 0).any():
            raise ValueError(f'{key}：指数点位必须大于零')
        features = [series / series.shift(5) - 1, series / series.shift(20) - 1,
                    series / series.rolling(60, min_periods=60).mean() - 1]
        return _mean([rank(feature, 120, calculation=name) for feature, name in
                      zip(features, ('5日涨跌幅', '20日涨跌幅', '60日均线偏离'))]), period

    def commodity(key):
        series, period, _ = load(key, 'USD')
        if (series <= 0).any():
            raise ValueError(f'{key}：价格必须大于零')
        return rank(series / series.shift(20) - 1, 120, calculation='20日涨跌幅'), period

    def ratio(key):
        series, period, _ = load(key, 'ratio')
        if (series.abs() > 1).any():
            raise ValueError(f'{key}：比例应在-1至1之间')
        return rank(series, 120), period

    def activity():
        series, period, _ = load('a_amount', 'CNY')
        if (series <= 0).any():
            raise ValueError('成交额须大于零')
        return _mean([rank(series, 120),
                      rank(series / series.rolling(20, min_periods=20).mean(), 120,
                           calculation='相对20日均额')]), period

    def margin():
        balance, period, coverage = load('a_margin_balance', 'CNY')
        buy, buy_period, buy_coverage = load('a_margin_buy_ratio', 'ratio')
        if period != buy_period or coverage != buy_coverage or '沪深' not in coverage:
            raise ValueError('两融需沪深同日、同覆盖口径')
        if (balance <= 0).any() or not buy.between(0, 1).all():
            raise ValueError('两融数值超出有效范围')
        return _mean([rank(balance / balance.shift(5) - 1, 120, calculation='5日余额变化'), rank(buy, 120)]), period

    def accounts():
        series, period, _ = load('a_new_accounts', 'accounts', True)
        if (series < 0).any():
            raise ValueError('新增开户不得为负')
        yearly = series / series.shift(12).replace(0, float('nan')) - 1
        return _mean([rank(series, 36), rank(yearly, 36, calculation='开户同比变化')]), period

    def composite(parts, same_period=True):
        results, errors = [], []
        for part in parts:
            try:
                results.append(part())
            except (ValueError, TypeError, ZeroDivisionError) as error:
                errors.append(str(error))
        if errors:
            raise ValueError('；'.join(dict.fromkeys(errors)))
        if same_period and len({period for _, period in results}) != 1:
            raise ValueError('复合指标各组成数据期不一致')
        return _mean([score for score, _ in results]), ' / '.join(sorted({period for _, period in results}))

    calculators = {
        'pmi': lambda: composite([lambda: pmi('cn_pmi'), lambda: pmi('us_pmi')]),
        'inflation': lambda: composite([
            lambda: month_change('cn_cpi_yoy', 'percent', True),
            lambda: composite([lambda: month_change('us_cpi_yoy', 'percent', True),
                               lambda: month_change('us_core_cpi_yoy', 'percent', True)])]),
        'policy': lambda: composite([lambda key=key: policy(key)
                                    for key in ('cn_policy_rate', 'us_policy_rate', 'eu_policy_rate', 'jp_policy_rate')]),
        'commodities': lambda: composite([lambda: commodity('gold'), lambda: commodity('oil')]),
        'us': lambda: composite([lambda: trend('sp500'), lambda: trend('nasdaq')]),
        'japan': lambda: trend('nikkei225'), 'korea': lambda: trend('kospi'),
        'sentiment': lambda: composite([lambda key=key: ratio(key)
                                       for key in ('a_breadth', 'a_newhigh_low_60', 'a_limit_balance')]),
        'activity': activity,
        'a_indices': lambda: composite([lambda key=key: trend(key)
                                       for key in ('sse', 'szse', 'chinext', 'star50', 'csi300')]),
        'margin': margin,
    }
    for key, calculate in calculators.items():
        group, name, weight = METRICS[key]
        try:
            score, period = calculate()
            if score is None:
                raise ValueError('缺可比历史：核算明细列出有效样本数与最低要求')
            scored[key] = score
            detail[key] = dict(name=name, group=group, weight=weight, score=score,
                               label=temperature_label(score), period=period, reason='历史分位规则，试验模型')
        except (ValueError, TypeError, ZeroDivisionError) as error:
            detail[key] = dict(name=name, group=group, weight=weight, score=None,
                               label='待补数据', period='', reason=str(error))
    result = aggregate_scores(scored)
    result.update(metrics=detail, calculation_audit=audit,
                  trade_date=cutoff.tz_convert('Asia/Shanghai').strftime('%Y-%m-%d'))
    result['input_signature'] = tuple(sorted({
        (record['indicator_id'], record['unit'], record['market_coverage'], urlparse(record['source_url']).netloc)
        for record in fresh.to_dict('records')
    }))
    result['reasons'] += ([f'缺少可评分指标：{len(result["missing"])}项'] if result['internal_score'] is None else
                          ['宏观支持度、海外趋势与A股热度综合；不代表买卖建议'])
    return result


def compare_temperature(current, previous, trading_dates):
    unavailable = dict(direction='缺可比上日', confirmed=False, stage_note='待连续交易日确认')
    dates = sorted(set(str(day) for day in trading_dates))
    day = current.get('trade_date')
    if not previous or day not in dates or dates.index(day) == 0:
        return unavailable
    if (previous.get('trade_date') != dates[dates.index(day)-1] or
        previous.get('rule_version') != current.get('rule_version') or
        previous.get('missing') != current.get('missing') or
        previous.get('input_signature') != current.get('input_signature') or
        current.get('internal_score') is None or previous.get('internal_score') is None):
        return unavailable
    change = current['internal_score'] - previous['internal_score']
    confirmed = current['label'] == previous['label']
    return dict(direction='升温' if change > 1e-8 else '降温' if change < -1e-8 else '持平',
                confirmed=confirmed,
                stage_note='连续交易日同档' if confirmed else '待连续交易日确认')
