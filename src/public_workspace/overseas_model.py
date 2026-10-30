"""Pure original completed-session overseas summary; no acquisition."""
import pandas as pd
from ..temperature_data import validate_observations

NAMES = {'sp500':'标普500','nasdaq':'纳斯达克','nikkei225':'日经225','kospi':'KOSPI'}


def overseas_summary(frame, cutoff):
    """Preview only: revised captured histories cannot claim point-in-time replay."""
    frame = validate_observations(frame)
    cutoff = pd.Timestamp(cutoff)
    rows = []
    for key, name in NAMES.items():
        subset = frame[frame['indicator_id'].eq(key)] if not frame.empty else frame
        if not subset.empty:
            subset = subset[(subset['completed_at'] <= cutoff) & (subset['published_at'] <= cutoff)]
            subset = subset.sort_values('published_at', kind='stable').drop_duplicates('data_period', keep='last').sort_values('data_period')
        row = dict(指标=name, 收盘点位='缺数据', 当日涨跌幅='缺数据', 交易日期='—',
                   **{'5日涨跌幅': '缺数据', '20日涨跌幅': '缺数据', '60日均线偏离': '缺数据'},
                   原始样本数=len(subset), 来源='—', 完成时间='—', 状态='缺已收盘数据')
        if not subset.empty:
            values = subset['value'].astype(float)
            last = subset.iloc[-1]
            row.update(收盘点位=f'{values.iloc[-1]:,.2f}', 交易日期=last['data_period'],
                       来源=last['source_url'], 完成时间=last['completed_at'].tz_convert('Asia/Shanghai').isoformat(),
                       状态='来源最新可取得；非实时')
            for n, column in ((1, '当日涨跌幅'), (5, '5日涨跌幅'), (20, '20日涨跌幅')):
                if len(values) > n:
                    row[column] = f'{(values.iloc[-1]/values.iloc[-n-1]-1)*100:+.2f}%'
            if len(values) >= 60:
                row['60日均线偏离'] = f'{(values.iloc[-1]/values.iloc[-60:].mean()-1)*100:+.2f}%'
        rows.append(row)
    return pd.DataFrame(rows)
