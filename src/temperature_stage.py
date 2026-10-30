"""Independent, experimental trend diagnostics. No temperature or trading signal."""
import pandas as pd
from src.temperature_data import observations_at, validate_observations

ANCHOR = '2024-09-24'
INDEX_NAMES = {'sse':'上证指数', 'szse':'深证成指', 'chinext':'创业板指',
               'star50':'科创50', 'csi300':'沪深300'}


def evaluate_trend_stage(observations, cutoff):
    cutoff = pd.Timestamp(cutoff)
    fresh = observations_at(observations, cutoff)
    known = validate_observations(observations)
    if not known.empty:
        known = known[(known['published_at'] <= cutoff) & (known['completed_at'] <= cutoff)]
        known = known.sort_values('published_at', kind='stable').drop_duplicates(['indicator_id','data_period'], keep='last')
    output = dict(label='待补指数历史', anchor=ANCHOR, rule_version='trend-experimental-v2-ma250',
                  indices=[], technology='待补科技指数历史', annual_line=dict(level=None,status='缺上证历史'))
    for key, name in INDEX_NAMES.items():
        records = known.loc[known['indicator_id'].eq(key)].sort_values('data_period') if not known.empty else known
        item = dict(indicator_id=key, name=name, stage='待补指数历史', reason='需覆盖观察起点及至少270个有效收盘；不得用单日快照判断')
        if (not records.empty and len(records) >= 270 and records['unit'].eq('points').all()
                and records['data_period'].str.fullmatch(r'\d{4}-\d{2}-\d{2}').all()
                and records.iloc[0]['data_period'] <= ANCHOR
                and records.iloc[-1]['data_period'] >= ANCHOR):
            last = records.iloc[-1]
            if fresh.loc[fresh['indicator_id'].eq(key) & fresh['data_period'].eq(last['data_period'])].empty:
                item['reason'] = '最新观测已过期'
            else:
                values = records['value'].astype(float)
                if (values <= 0).any():
                    item['reason'] = '指数点位须大于零'
                else:
                    cycle = records.loc[records['data_period'].ge(ANCHOR)]
                    peak = float(cycle['value'].max())
                    close = float(values.iloc[-1])
                    ma120 = values.rolling(120).mean()
                    ma250 = values.rolling(250).mean()
                    slope120 = float(ma120.iloc[-1]/ma120.iloc[-21]-1)
                    slope250 = float(ma250.iloc[-1]/ma250.iloc[-21]-1)
                    drawdown = close/peak-1
                    recent_low = float(values.iloc[-23:-3].min())
                    break_low = bool(values.iloc[-3:].lt(recent_low).all())
                    below = close < ma120.iloc[-1] and close < ma250.iloc[-1]
                    if below and slope120 < 0 and slope250 < 0:
                        stage = '下行趋势'
                    elif (close < ma250.iloc[-1] and slope250 < 0) or break_low:
                        stage = '结构转弱'
                    elif close >= ma120.iloc[-1] and close >= ma250.iloc[-1] and slope120 > 0 and slope250 >= 0 and drawdown >= -.05:
                        stage = '上升趋势'
                    else:
                        stage = '调整中'
                    item.update(stage=stage, close=close, period=last['data_period'], cycle_peak=peak,
                                cycle_peak_date=cycle.loc[cycle['value'].eq(peak),'data_period'].iloc[-1],
                                cycle_drawdown=drawdown, ma120=float(ma120.iloc[-1]), ma250=float(ma250.iloc[-1]),
                                slope120=slope120, slope250=slope250, recent_low=recent_low,
                                break_low=break_low, samples=len(records), source=last['source_url'],
                                reason='120/250日均线、20交易日均线斜率及近期低点；实验阈值待回测')
                    if key == 'sse':
                        below_sessions = 0
                        for is_below in (values < ma250).iloc[::-1]:
                            if not is_below:
                                break
                            below_sessions += 1
                        status = ('年线上方' if close >= ma250.iloc[-1] else
                                  '下行趋势确认' if below_sessions >= 5 and slope250 < 0 else
                                  '年线下方 · 趋势转弱')
                        output['annual_line'].update(level=float(ma250.iloc[-1]), status=status,
                            distance=close/ma250.iloc[-1]-1, below_sessions=below_sessions,
                            slope=slope250, period=last['data_period'])
        output['indices'].append(item)
    stages = [item['stage'] for item in output['indices']]
    if '待补指数历史' not in stages:
        output['label'] = next((label for label in ('下行趋势','结构转弱','上升趋势') if stages.count(label) >= 3), '调整中')
    tech = [item['stage'] for item in output['indices'] if item['indicator_id'] in ('star50','chinext')]
    if '待补指数历史' not in tech:
        output['technology'] = tech[0] if tech[0] == tech[1] else '科技指数分化'
    return output
