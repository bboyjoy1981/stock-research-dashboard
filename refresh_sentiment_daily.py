"""Resume BaoStock A-share sentiment research through the latest closed session.

The captured history is for latest research only. It is never backdated into
the point-in-time replay inventory.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import itertools
import json
import os
import socket
import tempfile
import time
from pathlib import Path

import pandas as pd

from src.temperature_store import load_observations, save_observations


ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT / 'data' / 'temperature' / 'research_ashare' / 'sentiment_20261011'
LATEST = ROOT / 'data' / 'temperature' / 'latest'
BASE_BARS = RESEARCH / 'daily_bars.csv.gz'
INDICATORS = ('a_breadth', 'a_newhigh_low_60', 'a_limit_balance')
FIELDS = 'date,code,close,preclose,pctChg,isST,tradestatus'

spec = importlib.util.spec_from_file_location('sentiment_capture_base', RESEARCH / 'capture_sentiment_history.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def _completed_target(now):
    local = now.tz_convert('Asia/Shanghai')
    day = local.date()
    if local.hour < 16:
        day -= pd.Timedelta(days=1)
    return day.isoformat()


def _read_increment(path):
    saved = {}
    if path.exists():
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                item = json.loads(line)
                if item['code'] in saved:
                    raise ValueError(f'重复证券记录：{path.name} {item["code"]}')
                saved[item['code']] = item['rows']
    return saved


def _stock_codes():
    first_seen = {}
    with gzip.open(BASE_BARS, 'rt', encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            first_seen.setdefault(row['code'], row['date'])
    for path in sorted(RESEARCH.glob('daily_bars_increment_*.jsonl')):
        for code, rows in _read_increment(path).items():
            first_seen.setdefault(code, rows[0][0] if rows else None)
    imports = sorted((ROOT / 'data' / 'imports').glob('stock_pool_*.csv'))
    if imports:
        with imports[-1].open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                digits = str(row.get('代码', '')).zfill(6)
                if digits.startswith(base.STARTER_PREFIXES['sh']):
                    first_seen.setdefault('sh.' + digits, None)
                elif digits.startswith(base.STARTER_PREFIXES['sz']):
                    first_seen.setdefault('sz.' + digits, None)
    return first_seen


def _fetch_rows(codes, path, start_day, target_day):
    saved = _read_increment(path)
    failures = []
    requests_in_session = 0
    consecutive_failures = 0
    started = time.monotonic()

    def relogin():
        nonlocal requests_in_session
        try:
            base.bs.logout()
        except (OSError, RuntimeError):
            pass
        login = base.bs.login()
        if login.error_code != '0':
            raise RuntimeError(f'BaoStock重新登录失败：{login.error_code} {login.error_msg}')
        requests_in_session = 0

    with path.open('a', encoding='utf-8') as handle:
        for index, code in enumerate(codes, 1):
            if code in saved:
                continue
            if requests_in_session >= 80:
                relogin()
            for attempt in range(3):
                try:
                    requests_in_session += 1
                    query = base.bs.query_history_k_data_plus(
                        code, FIELDS, start_day, target_day, frequency='d', adjustflag='3')
                    if query.error_code != '0':
                        raise RuntimeError(f'{query.error_code}: {query.error_msg}')
                    rows = list(query.data)
                    if any(row[0] < start_day or row[0] > target_day or row[1] != code for row in rows):
                        raise ValueError(f'{code} 返回日期或代码不符')
                    handle.write(json.dumps({'code': code, 'rows': rows}, ensure_ascii=False) + '\n')
                    handle.flush()
                    saved[code] = rows
                    consecutive_failures = 0
                    break
                except (OSError, ValueError, RuntimeError) as error:
                    if attempt == 2:
                        failures.append({'code': code, 'error': str(error)})
                        consecutive_failures += 1
                        if consecutive_failures >= 5:
                            raise RuntimeError(f'BaoStock连续失败{consecutive_failures}只，'
                                               f'最后错误：{code}: {error}；已保留采集断点')
                    else:
                        relogin()
                        time.sleep(0.5 * (attempt + 1))
            if index % 250 == 0:
                print(json.dumps({'event': 'progress', 'saved': len(saved), 'total': len(codes),
                                  'failed': len(failures),
                                  'latest_error': failures[-1] if failures else None,
                                  'elapsed_seconds': round(time.monotonic() - started, 1)}), flush=True)
            time.sleep(0.02)
    if failures or len(saved) != len(codes):
        raise RuntimeError(f'证券历史未采齐：{len(saved)}/{len(codes)}；失败{len(failures)}；未写入评分数据')
    return saved


def _ensure_published(target_day):
    """Avoid recording empty rows for every security before BaoStock publishes the close."""
    for code in ('sh.600000', 'sz.000001', 'sh.600519'):
        query = base.bs.query_history_k_data_plus(
            code, FIELDS, target_day, target_day, frequency='d', adjustflag='3')
        if query.error_code != '0':
            raise RuntimeError(f'BaoStock交易日预检失败：{query.error_code} {query.error_msg}')
        if any(row[0] == target_day for row in query.data):
            return
    raise RuntimeError(f'BaoStock尚未返回{target_day}已收盘日线，保留旧数据稍后重试')


def _fetch_batch_rows(codes, path, new_days):
    """One BaoStock all-A-stock daily request per completed trading day."""
    by_code = {code: [] for code in codes}
    expected = {'date', 'code', 'close', 'preclose', 'pctChg', 'isST',
                'tradestatus', 'adjustflag'}
    for day in new_days:
        response = base.bs.query_daily_history_k_AStock(date=day)
        if response.error_code != '0':
            raise RuntimeError(f'BaoStock全市场日线{day}：{response.error_code} {response.error_msg}')
        if not expected.issubset(response.fields):
            raise ValueError(f'BaoStock全市场日线字段不齐：{response.fields}')
        positions = {field: index for index, field in enumerate(response.fields)}
        rows = list(response.data)
        if len(rows) < 5000:
            raise RuntimeError(f'BaoStock尚未返回完整的{day}收盘日线：仅{len(rows)}只')
        seen = set()
        for item in rows:
            code = item[positions['code']]
            if item[positions['date']] != day or item[positions['adjustflag']] != '3':
                raise ValueError(f'{day}全市场日线日期或复权口径不符：{code}')
            if code in seen:
                raise ValueError(f'{day}全市场日线重复证券：{code}')
            seen.add(code)
            if base.stock_code(code) is None:
                continue
            codes.setdefault(code, day)
            by_code.setdefault(code, []).append(
                [item[positions[key]] for key in
                 ('date', 'code', 'close', 'preclose', 'pctChg', 'isST', 'tradestatus')]
            )
        print(json.dumps({'event': 'batch', 'day': day, 'source_rows': len(rows),
                          'eligible': len(seen)}), flush=True)
    partial = _read_increment(path)
    mismatches = [code for code, rows in partial.items() if rows != by_code.get(code, [])]
    if mismatches:
        raise RuntimeError(f'全市场接口与已有逐只采集不一致：{mismatches[:5]}；保留断点待核对')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         prefix='.daily_batch_', suffix='.jsonl',
                                         delete=False) as handle:
            temporary = Path(handle.name)
            for code, rows in by_code.items():
                handle.write(json.dumps({'code': code, 'rows': rows}, ensure_ascii=False) + '\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return codes


def _derive(trade_dates, codes, current_path, target_day):
    daily = {day: dict(breadth_sample=0, advancers=0, decliners=0,
                       newhl_sample=0, new_highs=0, new_lows=0,
                       limit_sample=0, limit_up=0, limit_down=0)
             for day in trade_dates}
    increments = [_read_increment(path) for path in sorted(RESEARCH.glob('daily_bars_increment_*.jsonl'))
                  if path != current_path and path.stem.split('_')[-1] < target_day.replace('-', '')]
    current = _read_increment(current_path)

    class NullWriter:
        def writerow(self, row):
            pass

    seen = set()
    with gzip.open(BASE_BARS, 'rt', encoding='utf-8', newline='') as handle:
        for code, entries in itertools.groupby(csv.DictReader(handle), key=lambda row: row['code']):
            if code not in codes:
                continue
            history = [[row[key] for key in ('date', 'code', 'close', 'preclose',
                                             'pctChg', 'isST', 'tradestatus')]
                       for row in entries]
            rows = history + [bar for batch in increments for bar in batch.get(code, [])] + current[code]
            _calculate(code, codes[code], rows, trade_dates, daily, NullWriter())
            seen.add(code)
    for code in set(codes) - seen:
        rows = [bar for batch in increments for bar in batch.get(code, [])] + current[code]
        _calculate(code, codes[code], rows, trade_dates, daily, NullWriter())
    return daily


def _calculate(code, first_seen, rows, trade_dates, daily, writer):
    first = first_seen or (rows[0][0] if rows else trade_dates[-1])
    ipo = first if first > '2026-01-05' else '1900-01-01'
    exchange, digits = code.split('.')
    security = dict(exchange=exchange, digits=digits, ipo=ipo, out='', name='')
    base.calculate_symbol(security, rows, trade_dates, daily, writer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', help='已完成交易日上限，格式 YYYY-MM-DD')
    args = parser.parse_args()
    if not BASE_BARS.exists():
        raise FileNotFoundError(f'缺少原始历史：{BASE_BARS}')
    captured = pd.Timestamp.now(tz='UTC')
    target_day = _completed_target(captured)
    if args.through:
        requested = pd.Timestamp(args.through).date().isoformat()
        if requested > target_day:
            raise ValueError(f'请求日期{requested}尚未收盘；最多可采{target_day}')
        target_day = requested
    existing = load_observations(LATEST)
    prior = existing[existing['indicator_id'].isin(INDICATORS)]
    last_day = prior['data_period'].max() if not prior.empty else None
    if last_day is None:
        raise RuntimeError('缺少既有情绪历史，不执行增量采集')
    if target_day <= last_day:
        print(json.dumps({'event': 'unchanged', 'latest_period': last_day}), flush=True)
        return
    socket.setdefaulttimeout(15)
    login = base.bs.login()
    if login.error_code != '0':
        raise RuntimeError(f'BaoStock登录失败：{login.error_code} {login.error_msg}')
    try:
        calendar = base.api_rows(base.bs.query_trade_dates(base.START, target_day), 'trade_dates')
        trade_dates = [row[0] for row in calendar if row[1] == '1' and base.START <= row[0] <= target_day]
        new_days = [day for day in trade_dates if day > last_day]
        if not new_days:
            print(json.dumps({'event': 'market_closed', 'latest_period': last_day}), flush=True)
            return
        target_day = trade_dates[-1]
        tag = target_day.replace('-', '')
        raw_path = RESEARCH / f'daily_bars_increment_{tag}.jsonl'
        report_path = RESEARCH / f'increment_report_{tag}.json'
        if report_path.exists():
            raise RuntimeError(f'报告已存在但研究库存仍停在{last_day}：{report_path}')
        codes = _stock_codes()
        print(json.dumps({'event': 'start', 'from': last_day, 'to': target_day,
                          'securities': len(codes), 'resumed': len(_read_increment(raw_path))}), flush=True)
        codes = _fetch_batch_rows(codes, raw_path, new_days)
    finally:
        base.bs.logout()

    base.END = target_day
    base.CAPTURE = pd.Timestamp.now(tz='UTC')
    daily = _derive(trade_dates, codes, raw_path, target_day)
    latest = daily[target_day]
    if min(latest['breadth_sample'], latest['newhl_sample'], latest['limit_sample']) < 5000:
        raise RuntimeError(f'{target_day}样本不足5000，未写入评分数据：{latest}')
    reconstructed = base.make_observations({last_day: daily[last_day]})
    prior_values = (prior[prior.data_period.eq(last_day)]
                    .sort_values('published_at').drop_duplicates('indicator_id', keep='last')
                    .set_index('indicator_id')['value'])
    reconstructed_values = reconstructed.set_index('indicator_id')['value']
    if set(prior_values.index) != set(INDICATORS) or any(
            abs(prior_values[key] - reconstructed_values[key]) > 1e-10 for key in INDICATORS):
        raise RuntimeError(f'{last_day}已核验情绪比率复算不一致，未写入新评分数据')
    frame = base.make_observations({day: daily[day] for day in new_days})
    if set(frame[frame.data_period.eq(target_day)].indicator_id) != set(INDICATORS):
        raise RuntimeError('最新交易日三项情绪指标不齐，未写入评分数据')
    report = dict(captured_at=base.CAPTURE.isoformat(), period=[new_days[0], target_day],
                  securities=len(codes), latest_sample=latest, observations=len(frame),
                  source='BaoStock未复权日线；仅用于最新研究，不回填历史时点复盘')
    save_observations(frame, LATEST)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'event': 'saved', **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
