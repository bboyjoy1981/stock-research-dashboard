"""Refresh captured A-share research history without backdating its publication time."""

from contextlib import redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
import sys

import pandas as pd

from src.temperature_store import load_observations


RESEARCH = Path(__file__).resolve().parents[1] / 'data' / 'temperature' / 'research_ashare'


def _completed_day(captured):
    local = captured.tz_convert('Asia/Shanghai')
    day = local.date()
    if local.hour < 16:
        day -= pd.Timedelta(days=1)
    while pd.Timestamp(day).weekday() >= 5:
        day -= pd.Timedelta(days=1)
    return day.isoformat()


def refresh_ashare_research(directory, captured_at=None):
    """Capture indexes, exchange turnover and margin; source dates stay explicit."""
    captured = pd.Timestamp.now(tz='UTC') if captured_at is None else pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError('抓取时间必须带时区')
    captured = captured.tz_convert('UTC')
    directory = Path(directory)
    before = load_observations(directory)
    source = RESEARCH / 'capture_research.py'
    spec = spec_from_file_location('capture_research', source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = directory
    module.END = _completed_day(captured)
    module.CAPTURE = captured
    statuses = []
    errors = []
    with redirect_stdout(StringIO()):
        try:
            module.main()
        except (OSError, ValueError, KeyError) as error:
            errors.append(f'A股指数或两融：{error}')
        # The exchange turnover source is independent of the index API's amount field.
        try:
            previous = sys.modules.get('capture_research')
            sys.modules['capture_research'] = module
            supplement_spec = spec_from_file_location('temperature_supplement_official',
                                                       RESEARCH / 'supplement_official.py')
            supplement = module_from_spec(supplement_spec)
            supplement_spec.loader.exec_module(supplement)
            supplement.main()
        except (OSError, ValueError, KeyError) as error:
            errors.append(f'交易所成交额：{error}')
        finally:
            if previous is None:
                sys.modules.pop('capture_research', None)
            else:
                sys.modules['capture_research'] = previous
    after = load_observations(directory)
    added = max(len(after) - len(before), 0)
    for key in ('sse', 'szse', 'chinext', 'star50', 'csi300', 'a_amount',
                'a_margin_balance', 'a_margin_buy_ratio'):
        rows = after.loc[after['indicator_id'].eq(key)]
        period = rows['data_period'].max() if not rows.empty else '缺数据'
        latest_row = rows.sort_values('data_period').iloc[-1] if not rows.empty else None
        updated = latest_row is not None and latest_row['fetched_at'] >= captured
        lagging = latest_row is not None and period < module.END
        statuses.append(dict(来源='A股公开数据', 指标=key,
                             地址=latest_row['source_url'] if latest_row is not None else '',
                             状态='来源滞后' if lagging else '本次取得' if updated else '沿用已有' if latest_row is not None else '缺数据',
                             说明=f'最新数据期 {period}；本次抓取目标 {module.END}'))
    return dict(observations=after, saved_count=added, source_status=statuses, errors=errors)
