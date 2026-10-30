"""Common-period research views; never fill values or alter stored vintages."""
from src.temperature_data import observations_at


def align_macro_history(frame, cutoff):
    current = observations_at(frame, cutoff)
    result = frame.copy()
    audit = []
    groups = [('央行政策', ('cn_policy_rate', 'us_policy_rate', 'eu_policy_rate', 'jp_policy_rate')),
              ('黄金与原油', ('gold', 'oil'))]
    for name, keys in groups:
        series = {key: current[current.indicator_id.eq(key)] for key in keys}
        if not any(len(value) for value in series.values()):
            continue
        common = set.intersection(*(set(value.data_period) for value in series.values()))
        date = max(common) if common else None
        audit.append({'组合': name, '共同数据期': date or '无共同有效期；不对齐',
                      '指标各自最新期': ' / '.join(f'{key}:{value.data_period.max() if len(value) else "缺数据"}'
                                                for key, value in series.items()),
                      '处理': '仅截取各指标截至共同期的真实历史；不前填、不补零' if date else '保留缺口'})
        if date:
            result = result[~(result.indicator_id.isin(keys) & result.data_period.gt(date))]
    return result, audit


def align_shared_daily_history(frame, cutoff, keys):
    """Use the latest still-valid shared trading date, without filling gaps."""
    current = observations_at(frame, cutoff)
    series = {key: current[current.indicator_id.eq(key)] for key in keys}
    if any(value.empty for value in series.values()):
        return frame, None
    common = set.intersection(*(set(value.data_period) for value in series.values()))
    if not common:
        return frame, None
    date = max(common)
    aligned = frame[~(frame.indicator_id.isin(keys) & frame.data_period.gt(date))]
    return aligned, date
