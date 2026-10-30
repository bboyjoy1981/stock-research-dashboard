"""Explicit latest-research refresh; never relabel captures as historical releases."""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from src.overseas_temperature import collect_overseas_sources
from src.ism_history import collect_ism_history
from src.temperature_ashare_refresh import refresh_ashare_research
from src.temperature_history import collect_history_sources
from src.temperature_store import save_observations


def refresh_latest_sources(directory, captured_at=None, include_ashare=False):
    captured = pd.Timestamp.now(tz='UTC') if captured_at is None else pd.Timestamp(captured_at)
    if captured.tzinfo is None or pd.isna(captured):
        raise ValueError('抓取时间必须带时区')
    captured = captured.tz_convert('UTC')

    def fetch(item):
        name, collector = item
        try:
            return name, collector(captured_at=captured), None
        except (requests.RequestException, ValueError, OSError, KeyError) as error:
            return name, None, f'{name}：{error}'

    statuses, errors, saved = [], [], 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, [('宏观历史', collect_history_sources),
                                        ('海外指数历史', collect_overseas_sources),
                                        ('美国制造业PMI历史', collect_ism_history)]))
    for name, result, error in results:
        if error:
            errors.append(error)
            statuses.append(dict(来源=name, 状态='失败', 说明=error))
            continue
        statuses.extend(result['source_status'])
        errors.extend(result.get('errors', []))
        for status in result['source_status']:
            if status.get('状态') == '失败':
                errors.append(f"{status.get('指标', name)}：{status.get('说明', '采集失败')}")
        try:
            save_observations(result['observations'], directory)
            saved += len(result['observations'])
        except (OSError, ValueError, KeyError) as error:
            message = f'{name}保存失败，保留旧数据：{error}'
            errors.append(message)
            statuses.append(dict(来源=name, 状态='保存失败', 说明=message))
    if include_ashare:
        try:
            ashare = refresh_ashare_research(directory, captured)
            statuses.extend(ashare['source_status'])
            errors.extend(ashare['errors'])
            saved += ashare['saved_count']
        except (OSError, ValueError, KeyError) as error:
            errors.append(f'A股历史更新失败，保留旧数据：{error}')
    return dict(saved_count=saved, source_status=statuses, errors=errors,
                fetched_at=captured.isoformat())
