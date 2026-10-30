"""Capture one verified A-share capital-flow snapshot without Streamlit."""
from __future__ import annotations

from datetime import datetime, time
import json
import msvcrt
from pathlib import Path
from zoneinfo import ZoneInfo

import baostock as bs
import pandas as pd

from src.capital_flow_source import CAPITAL_FLOW_SECTORS, fetch_capital_flow_snapshot_with_diagnostics
from src.importers import load_capital_replay, save_capital_replay


ROOT = Path(__file__).resolve().parent
DIRECTORY = ROOT / 'data' / 'capital_replay'
ZONE = ZoneInfo('Asia/Shanghai')
STATUS_PATH = DIRECTORY / 'capture_status.json'


def record_status(status, **details):
    previous = json.loads(STATUS_PATH.read_text(encoding='utf-8')) if STATUS_PATH.exists() else {}
    failures = previous.get('consecutive_failures', 0) + 1 if status == 'failed' else 0
    payload = {'status': status, 'checked_at': datetime.now(ZONE).isoformat(),
               'consecutive_failures': failures, **details}
    temporary = STATUS_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    temporary.replace(STATUS_PATH)
    return payload


def trading_session(now):
    if now.weekday() >= 5:
        return False
    clock = now.time()
    return time(9, 30) <= clock <= time(11, 30) or time(13) <= clock <= time(15, 5)


def confirmed_trading_day(day):
    cache = DIRECTORY / f'trading_day_{day.isoformat()}.json'
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))['is_trading_day']
    login = bs.login()
    if login.error_code != '0':
        raise RuntimeError(f'BaoStock 交易日历登录失败：{login.error_msg}')
    try:
        result = bs.query_trade_dates(start_date=day.isoformat(), end_date=day.isoformat())
        if result.error_code != '0' or not result.next():
            raise RuntimeError(f'BaoStock 交易日历查询失败：{result.error_msg}')
        row = dict(zip(result.fields, result.get_row_data()))
        flag = row.get('is_trading_day')
        if flag not in ('0', '1'):
            raise RuntimeError('交易日历返回无效标志')
        is_trading_day = flag == '1'
    finally:
        bs.logout()
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({'date': day.isoformat(), 'is_trading_day': is_trading_day}), encoding='utf-8')
    return is_trading_day


def main():
    now = datetime.now(ZONE)
    if not trading_session(now):
        print(json.dumps({'status': 'outside_session', 'at': now.isoformat()}, ensure_ascii=False))
        return 0
    if not confirmed_trading_day(now.date()):
        print(json.dumps({'status': 'market_closed', 'date': now.date().isoformat()}, ensure_ascii=False))
        return 0

    previous = load_capital_replay(str(DIRECTORY))
    bucket = now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)
    bucket_end = bucket + pd.Timedelta(minutes=5)
    today = previous.loc[previous['时间'].astype(str).str.startswith(now.date().isoformat())] if '时间' in previous else pd.DataFrame()
    if not today.empty:
        timestamps = pd.to_datetime(today['时间'], errors='coerce').dropna()
        if ((timestamps >= bucket.replace(tzinfo=None)) & (timestamps < bucket_end.replace(tzinfo=None))).any():
            print(json.dumps({'status': 'already_saved', 'bucket': bucket.isoformat()}, ensure_ascii=False))
            return 0
    preferred = '东方财富'
    if not today.empty and '数据来源' in today:
        sources = today.sort_values('时间')['数据来源'].dropna().astype(str)
        if not sources.empty and sources.iloc[-1].startswith('同花顺'):
            preferred = '同花顺'
    errors = []
    for provider in (preferred, '同花顺' if preferred == '东方财富' else '东方财富'):
        try:
            result = fetch_capital_flow_snapshot_with_diagnostics(as_of=now, preferred_provider=provider)
            frame = result['snapshot']
            diagnostics = result['diagnostics']
            missing = sorted(set(CAPITAL_FLOW_SECTORS) - set(frame.get('行业', [])))
            if missing or frame.empty or frame['净流入额'].isna().any():
                raise ValueError('目标板块不完整：' + '、'.join(missing))
            path = save_capital_replay(frame, str(DIRECTORY))
            record_status('saved', time=frame['时间'].iloc[0], provider=provider,
                          sectors=len(frame), path=path)
            print(json.dumps({'status': 'saved', 'time': frame['时间'].iloc[0], 'provider': provider,
                              'sectors': len(frame), 'path': path, 'diagnostics': len(diagnostics)}, ensure_ascii=False))
            return 0
        except Exception as error:
            errors.append(f'{provider}: {str(error)[:180]}')
    payload = record_status('failed', at=now.isoformat(), errors=errors)
    print(json.dumps(payload, ensure_ascii=False))
    return 1


if __name__ == '__main__':
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (DIRECTORY / '.capture.lock').open('a+b') as lock:
        lock.seek(0)
        if lock.read(1) == b'':
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print(json.dumps({'status': 'already_running'}, ensure_ascii=False))
            raise SystemExit(0)
        try:
            try:
                code = main()
            except Exception as error:
                payload = record_status('failed', error=str(error)[:300])
                print(json.dumps(payload, ensure_ascii=False))
                code = 1
            raise SystemExit(code)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
