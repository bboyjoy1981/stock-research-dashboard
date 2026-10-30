"""Dated public index snapshots, independent of stock imports."""
from pathlib import Path
import re
from datetime import datetime
from urllib.request import Request, urlopen
import pandas as pd

URL = 'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,sh000300,bj899050'


def parse_index_quotes(payload):
    rows = []
    for symbol, body in re.findall(r'v_(\w+)="([^"]+)";', payload):
        fields = body.split('~')
        if len(fields) < 35:
            continue
        try:
            day = datetime.strptime(fields[30], '%Y%m%d%H%M%S').date().isoformat()
            row = dict(代码=symbol, 名称=fields[1], 交易日期=day, 源时间=fields[30], 来源='腾讯公开行情')
            for label, position in [('价格', 3), ('昨收', 4), ('今开', 5), ('涨跌', 31), ('涨跌幅', 32), ('最高', 33), ('最低', 34)]:
                row[label] = float(fields[position])
            rows.append(row)
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows)


def fetch_and_save_indices(directory, expected_date):
    with urlopen(Request(URL, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15) as response:
        frame = parse_index_quotes(response.read().decode('gbk'))
    if len(frame) != 6 or set(frame['交易日期']) != {expected_date}:
        raise ValueError('指数不完整或源交易日期不匹配；未保存')
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / ('indices_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.csv')
    frame.to_csv(path, index=False, encoding='utf-8-sig')
    return path


def load_index_snapshot(directory, trade_date):
    for path in sorted(Path(directory).glob('indices_*.csv'), reverse=True):
        frame = pd.read_csv(path, encoding='utf-8-sig')
        selected = frame.loc[frame['交易日期'].astype(str).eq(str(trade_date))]
        if not selected.empty:
            return selected
    return pd.DataFrame()
