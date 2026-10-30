"""Descriptive, scope-preserving historical comparisons (not temperature scores)."""

import pandas as pd
import re
import math

from src.temperature_data import observations_at


def parse_account_reference(records):
    result = {}
    for record in records:
        term = record.get('TERM', '')
        if not re.fullmatch(r'\d{4}\.\d{2}', term) or term.replace('.', '') > record['MDATE']:
            continue
        value = float(record['A_ACCT']) * 10000
        if not math.isfinite(value) or value < 0:
            raise ValueError('无效开户数')
        period = term.replace('.', '-')
        if period in result and result[period] != value:
            raise ValueError('同月开户数冲突')
        result[period] = value
    return result


def compare_2015_accounts(current):
    """Manually verified SSE 2016 yearbook, printed p563; A-share column.

    Descriptive research only, not a publication-vintage observation or score.
    Monthly printed sum is 4005.60; printed annual total is 4005.59 (rounding).
    """
    values = [100.37, 56.62, 246.14, 719.86, 673.81, 711.81,
              327.11, 227.03, 188.17, 190.71, 273.27, 290.70]
    mean = sum(values) * 10000 / 12
    peak = max(values) * 10000
    spring_mean = sum(values[3:6]) * 10000 / 3
    summer_mean = sum(values[6:9]) * 10000 / 3
    return dict(mean=mean, peak=peak, peak_period='2015-04', count=12,
                spring_mean=spring_mean, summer_mean=summer_mean,
                spring_difference_pct=(current / spring_mean - 1) * 100,
                summer_difference_pct=(current / summer_mean - 1) * 100,
                difference_pct=(current / mean - 1) * 100,
                peak_difference_pct=(current / peak - 1) * 100,
                label='低于2015年月均，远低于开户峰值' if current < mean and current < peak * .5
                else '低于2015年月均' if current < mean else '不低于2015年月均',
                source='https://www.sse.com.cn/aboutus/publication/yearly/documents/c/10061078/files/08c138fe02fa460aa1c217eaf20b2b69.pdf')


def format_comparison_value(value, unit):
    if unit == 'CNY':
        return f'{value/1e12:,.2f}万亿元' if abs(value) >= 1e12 else f'{value/1e8:,.2f}亿元'
    if unit == 'accounts':
        return f'{value/1e4:,.2f}万户'
    if unit == 'ratio':
        return f'{value*100:.2f}%'
    if unit == 'points':
        return f'{value:,.2f}点'
    return f'{value:,.2f} {unit}'


def compare_history(frame, cutoff, indicator_id, start, end, minimum):
    fresh = observations_at(frame, cutoff)
    selected = fresh[fresh['indicator_id'].eq(indicator_id)].sort_values('data_period')
    result = dict(label='暂不可比', reason='没有有效的当前数据', count=0)
    if selected.empty:
        return result
    current = selected.iloc[-1]
    history = selected[(selected['data_period'] >= start) &
                       (selected['data_period'] <= end) &
                       (selected['data_period'] < current['data_period'])]
    result.update(current=float(current['value']), current_period=current['data_period'],
                  count=len(history), scope=current['market_coverage'], unit=current['unit'])
    if len(history) < minimum:
        result['reason'] = f'请求区间 {start} 至 {end}：仅 {len(history)} 个有效样本，至少需要 {minimum} 个；不以其他年份替代'
        return result
    mean = float(history['value'].mean())
    peak = history.loc[history['value'].idxmax()]
    percentile = float(((history['value'] < current['value']).sum() +
                        .5 * (history['value'] == current['value']).sum()) / len(history))
    result.update(mean=mean, difference_pct=(float(current['value']) / mean - 1) * 100 if mean else None,
                  peak=float(peak['value']), peak_period=peak['data_period'],
                  start=history['data_period'].min(), end=history['data_period'].max(),
                  percentile=percentile,
                  label='高于参考期常态' if percentile >= .8 else '低于参考期常态' if percentile <= .2 else '接近参考期常态',
                  reason='按参考期样本分位：低于20% / 20%—80% / 高于80%；描述原始水平，不等于牛熊或投资建议')
    return result
