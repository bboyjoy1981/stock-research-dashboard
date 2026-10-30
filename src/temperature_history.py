"""Captured historical datasets for current research, never fabricated PIT releases."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO, StringIO
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd
import requests

from src.temperature_data import validate_observations
from src.temperature_http import get_public
from src.temperature_pbc_policy import collect_pbc_policy, INDEX_URL as PBC_INDEX_URL

SOURCES = {
    'us_cpi_yoy': ('CPIAUCNS', 'percent', 'CPI-U全项目；美国城市平均；同比；未季调', 'cpi'),
    'us_core_cpi_yoy': ('CPILFENS', 'percent', 'CPI-U除食品能源；美国城市平均；同比；未季调', 'cpi'),
    'us_policy_rate': ('DFEDTARU', 'percent', '美联储联邦基金目标区间上限；月末', 'policy'),
    'eu_policy_rate': ('ECBDFR', 'percent', '欧洲央行存款便利利率；月末；固定口径非拼接主政策工具', 'policy'),
    'oil': ('DCOILBRENTEU', 'USD', 'EIA布伦特欧洲现货FOB；美元/桶；日价格', 'daily'),
    'gold': ('close_usd_per_troy_oz', 'USD', 'GoldPrice.com日价格；LBMA fixes与Metals.dev组合源；美元/金衡盎司', 'daily'),
}


def source_url(key):
    return ('https://www.goldprice.com/gold-price-history' if key == 'gold'
            else f'https://fred.stlouisfed.org/series/{SOURCES[key][0]}')


def parse_history_csv(text, key, captured_at):
    captured = pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError('抓取时间必须带时区')
    captured = captured.tz_convert('UTC')
    column, unit, coverage, kind = SOURCES[key]
    table = pd.read_csv(StringIO(text), comment='#', na_values=['.', ''])
    date_column = 'date' if key == 'gold' else 'observation_date'
    if date_column not in table or column not in table:
        raise ValueError('来源字段不符，未采用历史')
    dates = pd.to_datetime(table[date_column], errors='coerce')
    values = pd.to_numeric(table[column], errors='coerce')
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError('日期无效或重复')
    if (values.notna() & ~np.isfinite(values)).any():
        raise ValueError('非有限值')
    if kind != 'policy' and (values.dropna() <= 0).any():
        raise ValueError('价格或指数必须大于零')
    series = pd.Series(values.to_numpy(), index=dates).sort_index()
    if kind == 'cpi':
        periods = series.index.to_period('M')
        if periods.duplicated().any():
            raise ValueError('月度指数期重复')
        series.index = periods
        series = series.reindex(pd.period_range(periods.min(), periods.max(), freq='M'))
        series = ((series / series.shift(12) - 1) * 100).round(1).dropna().tail(120)
    elif kind == 'policy':
        series = series.dropna().groupby(series.index.to_period('M')).last()
        series = series[series.index < captured.tz_localize(None).to_period('M')].tail(120)
    else:
        series = series[series.index.dayofweek < 5].dropna().tail(400)
    records = []
    for date, value in series.items():
        if isinstance(date, pd.Period):
            period = str(date)
            completed = date.end_time.tz_localize('UTC')
        else:
            period = date.strftime('%Y-%m-%d')
            completed = date.tz_localize('UTC') + pd.Timedelta(hours=23, minutes=59)
        if completed > captured:
            continue
        records.append(dict(indicator_id=key, value=float(value), unit=unit,
            market_coverage=coverage, data_period=period, source_url=source_url(key),
            published_at=captured, completed_at=completed, fetched_at=captured,
            valid_until=captured + pd.Timedelta(days=1), revision=False,
            version='capture-' + hashlib.sha256(f'{period}|{value}|{coverage}'.encode()).hexdigest()[:16],
            publication_basis='captured_dataset',
            calculation='未季调指数同比（12月变化），按BLS公布精度四舍五入至一位小数' if kind == 'cpi' else '原始价格/利率；政策取已完整月份最后观测',
            validity_basis='本次捕获后24小时需重新核验；不是原始发布版本'))
    if not records:
        raise ValueError('未取得已完成期间的有效数据')
    return validate_observations(pd.DataFrame(records))


def collect_history_sources(captured_at=None):
    captured = pd.Timestamp.now(tz='UTC') if captured_at is None else pd.Timestamp(captured_at)
    def fetch(key):
        url = ('https://www.goldprice.com/gold-price-history.csv' if key == 'gold'
               else f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={SOURCES[key][0]}')
        try:
            response = get_public(url, timeout=(5, 15))
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError('历史文件过大')
            frame = parse_history_csv(response.text, key, captured)
            return frame, dict(指标=key, 来源=source_url(key), 状态='已取得历史',
                               样本数=len(frame), 最近数据期=frame.iloc[-1]['data_period'])
        except (requests.RequestException, ValueError) as error:
            return pd.DataFrame(), dict(指标=key, 来源=source_url(key), 状态='失败', 说明=str(error))
    def fetch_bis_japan():
        url = 'https://data.bis.org/static/bulk/WS_CBPOL_csv_col.zip'
        try:
            response = get_public(url, timeout=(5, 20))
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError('BIS政策利率文件过大')
            with ZipFile(BytesIO(response.content)) as archive:
                text = archive.read('WS_CBPOL_csv_col.csv').decode('utf-8-sig')
            frame = parse_bis_japan(text, captured)
            return frame, dict(指标='jp_policy_rate', 来源=url, 状态='已取得历史',
                               样本数=len(frame), 最近数据期=frame.iloc[-1]['data_period'])
        except (requests.RequestException, ValueError, BadZipFile, KeyError, UnicodeError) as error:
            return pd.DataFrame(), dict(指标='jp_policy_rate', 来源=url, 状态='失败', 说明=str(error))

    def fetch_pbc_policy():
        try:
            frame = collect_pbc_policy(captured)
            return frame, dict(指标='cn_policy_rate', 来源=PBC_INDEX_URL, 状态='已核验公告',
                               样本数=len(frame), 最近数据期=frame.iloc[-1]['data_period'])
        except (requests.RequestException, ValueError, KeyError) as error:
            return pd.DataFrame(), dict(指标='cn_policy_rate', 来源=PBC_INDEX_URL,
                                        状态='失败', 说明=str(error))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, key) for key in SOURCES]
        futures.append(pool.submit(fetch_bis_japan))
        futures.append(pool.submit(fetch_pbc_policy))
        results = [future.result() for future in futures]
    frames = [frame for frame, _ in results if not frame.empty]
    return dict(observations=validate_observations(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()),
                source_status=[status for _, status in results], fetched_at=captured.isoformat())


def parse_bis_japan(text, captured_at):
    captured = pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError('抓取时间必须带时区')
    captured = captured.tz_convert('UTC')
    table = pd.read_csv(StringIO(text), low_memory=False)
    selected = table.loc[table['FREQ'].eq('M') & table['REF_AREA'].eq('JP')]
    if len(selected) != 1:
        raise ValueError('缺唯一日本月度政策利率序列')
    row = selected.iloc[0]
    periods = [column for column in table.columns if len(column) == 7 and column[4] == '-']
    records = []
    for period in periods:
        value = pd.to_numeric(row[period], errors='coerce')
        completed = pd.Period(period, freq='M').end_time.tz_localize('UTC')
        if pd.isna(value) or completed > captured:
            continue
        records.append(dict(indicator_id='jp_policy_rate', value=float(value), unit='percent',
            market_coverage='BIS转发日本银行短期政策利率；月末；工具变迁见编制说明',
            data_period=period, source_url='https://data.bis.org/topics/CBPOL',
            published_at=captured, completed_at=completed, fetched_at=captured,
            valid_until=captured + pd.Timedelta(days=1), revision=False,
            version='capture-' + hashlib.sha256(f'{period}|{value}'.encode()).hexdigest()[:16],
            publication_basis='captured_dataset', compilation=str(row['COMPILATION']),
            attribution='Source: BIS; 中文说明不是BIS官方翻译；无关联或背书'))
    if not records:
        raise ValueError('日本政策利率无有效历史')
    return validate_observations(pd.DataFrame(records[-120:]))
