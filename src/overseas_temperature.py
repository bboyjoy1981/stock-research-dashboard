"""On-demand completed-session data; never invent historical publication times."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import StringIO
import math

import numpy as np
import pandas as pd
import requests

from src.temperature_data import validate_observations
from src.temperature_http import get_public

SOURCES = {
    'sp500': dict(name='标普500', url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500',
                  page='https://fred.stlouisfed.org/series/SP500', column='SP500',
                  date='observation_date', zone='America/New_York', close='16:00',
                  coverage='S&P500价格指数；FRED转发S&P DJI；日收盘'),
    'nasdaq': dict(name='纳斯达克', url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQCOM',
                   page='https://fred.stlouisfed.org/series/NASDAQCOM', column='NASDAQCOM',
                   date='observation_date', zone='America/New_York', close='16:00',
                   coverage='NASDAQ Composite价格指数；FRED转发Nasdaq；日收盘'),
    'nikkei225': dict(name='日经225',
                      url='https://indexes.nikkei.co.jp/nkave/historical/nikkei_stock_average_daily_jp.csv',
                      page='https://indexes.nikkei.co.jp/nkave/index/profile?idx=nk225',
                      column='終値', date='データ日付', zone='Asia/Tokyo', close='15:30',
                      coverage='Nikkei225价格指数；日经官方；日收盘'),
}
from .public_workspace.overseas_model import NAMES,overseas_summary
KOSPI_CHART = 'https://api.stock.naver.com/chart/domestic/index/KOSPI?periodType=dayCandle'
KOSPI_PAGE = 'https://m.stock.naver.com/domestic/index/KOSPI/total'


def parse_daily_csv(text, key, captured_at):
    captured = pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError('采集时间必须带时区')
    captured = captured.tz_convert('UTC')
    spec = SOURCES[key]
    table = pd.read_csv(StringIO(text), na_values=['.', ''])
    if spec['date'] not in table or spec['column'] not in table:
        raise ValueError('公开日收盘文件字段不匹配，未采用数据')
    dates = pd.to_datetime(table[spec['date']], errors='coerce')
    values = pd.to_numeric(table[spec['column']], errors='coerce')
    # The publisher's copyright footer is not a missing price or trading session.
    valid = dates.notna() & values.notna()
    if ((values[valid] <= 0) | ~np.isfinite(values[valid])).any():
        raise ValueError('指数点位不合法')
    clean = pd.DataFrame({'date': dates[valid], 'value': values[valid]}).sort_values('date')
    if clean['date'].duplicated().any():
        raise ValueError('同一交易日存在重复收盘值')
    records = []
    hour, minute = map(int, spec['close'].split(':'))
    for row in clean.tail(400).itertuples(index=False):
        # Conservative regular-close bound: shortened sessions are only admitted
        # after regular close too. No business-day guess fills a holiday.
        completed = row.date.tz_localize(spec['zone']) + pd.Timedelta(hours=hour, minutes=minute)
        if completed > captured:
            continue
        records.append(dict(indicator_id=key, value=row.value, unit='points',
            data_period=row.date.strftime('%Y-%m-%d'), source_url=spec['page'],
            market_coverage=spec['coverage'], completed_at=completed,
            published_at=captured, fetched_at=captured,
            valid_until=completed + pd.Timedelta(days=7),
            version='capture-' + hashlib.sha256(f'{row.date}|{row.value}'.encode()).hexdigest()[:16],
            revision=False, publication_basis='captured_dataset'))
    if not records:
        raise ValueError('未取得已完成交易时段的有效收盘值')
    # Old historical samples must have a valid contract even after freshness
    # expires. They are not current observations; scorer checks latest freshness.
    for record in records:
        record['valid_until'] = max(record['valid_until'], captured + pd.Timedelta(days=1))
    return validate_observations(pd.DataFrame(records))


def parse_kospi_chart(payload, captured_at):
    """Read dated Naver KOSPI daily closes, excluding the unfinished Seoul session."""
    captured = pd.Timestamp(captured_at)
    if captured.tzinfo is None or pd.isna(captured):
        raise ValueError('采集时间必须带时区')
    captured = captured.tz_convert('UTC')
    if not isinstance(payload, dict) or payload.get('code') != 'KOSPI' or payload.get('periodType') != 'dayCandle':
        raise ValueError('KOSPI日线代码或周期不匹配')
    prices = payload.get('priceInfos')
    if not isinstance(prices, list):
        raise ValueError('KOSPI日线字段不匹配')
    records = []
    seen = set()
    for item in prices:
        if not isinstance(item, dict) or 'localDate' not in item or 'closePrice' not in item:
            raise ValueError('KOSPI日线记录字段不匹配')
        value = float(item['closePrice'])
        if not math.isfinite(value) or value <= 0:
            raise ValueError('KOSPI收盘点位不合法')
        local_date = pd.to_datetime(item['localDate'], format='%Y%m%d', errors='raise').date()
        period = local_date.isoformat()
        if period in seen:
            raise ValueError('KOSPI同日重复收盘值')
        seen.add(period)
        # Naver can include a live daily bar. Wait beyond the regular 15:30 close.
        completed = pd.Timestamp(period, tz='Asia/Seoul') + pd.Timedelta(hours=16, minutes=30)
        if completed > captured:
            continue
        records.append(dict(indicator_id='kospi', value=value, unit='points',
            data_period=period, source_url=KOSPI_PAGE,
            market_coverage='KOSPI broad market price index; daily close; public Naver market-data capture of KRX index; historical revisions not independently verified',
            completed_at=completed, published_at=captured, fetched_at=captured,
            valid_until=max(completed + pd.Timedelta(days=7), captured + pd.Timedelta(days=7)),
            version='naver-kospi-' + hashlib.sha256(f'{period}|{value}'.encode()).hexdigest()[:16],
            revision=False, publication_basis='captured_dataset'))
    if len(records) < 60:
        raise ValueError(f'KOSPI有效已收盘历史不足60日：{len(records)}日')
    records.sort(key=lambda row: row['data_period'])
    return validate_observations(pd.DataFrame(records))


def collect_kospi_source(captured_at=None):
    captured = pd.Timestamp.now(tz='UTC') if captured_at is None else pd.Timestamp(captured_at)
    status = dict(来源='KOSPI', 地址=KOSPI_PAGE, 状态='待采集', 说明='')
    try:
        response = get_public(KOSPI_CHART, timeout=(5, 15),
                              headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise ValueError('KOSPI响应过大')
        frame = parse_kospi_chart(response.json(), captured)
        status.update(状态='已取得已收盘序列',
                      说明=f"最新可取得：{frame.iloc[-1]['data_period']}；{len(frame)}条；原始历史发布版本未核验")
        return frame, status, None
    except (requests.RequestException, ValueError, TypeError) as error:
        message = f'KOSPI：{error}'
        status.update(状态='采集失败', 说明=message)
        return pd.DataFrame(), status, message


def collect_overseas_sources(captured_at=None):
    captured = pd.Timestamp.now(tz='UTC') if captured_at is None else pd.Timestamp(captured_at)

    def fetch(item):
        key, spec = item
        status = dict(来源=spec['name'], 地址=spec['page'], 状态='待采集', 说明='')
        try:
            response = get_public(spec['url'], timeout=(5, 15))
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError('文件过大，拒绝解析')
            encoding = 'cp932' if key == 'nikkei225' else 'utf-8-sig'
            frame = parse_daily_csv(response.content.decode(encoding), key, captured)
            last = frame.iloc[-1]['data_period']
            status.update(状态='已取得已收盘序列', 说明=f'最新可取得：{last}；{len(frame)}条；原始历史发布版本未核验')
            return frame, status, None
        except (requests.RequestException, ValueError, UnicodeError) as error:
            message = f"{spec['name']}：{error}"
            status.update(状态='采集失败', 说明=message)
            return pd.DataFrame(), status, message

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, SOURCES.items()))
    frames = [frame for frame, _, _ in results if not frame.empty]
    statuses = [status for _, status, _ in results]
    kospi, status, error = collect_kospi_source(captured)
    if not kospi.empty:
        frames.append(kospi)
    results.append((kospi, status, error))
    statuses.append(status)
    return dict(observations=validate_observations(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()),
                source_status=statuses, errors=[error for _, _, error in results if error],
                fetched_at=captured.isoformat())
