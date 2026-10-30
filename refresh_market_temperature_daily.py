"""Refresh the complete latest market-temperature research inventory."""
from __future__ import annotations

import json
from pathlib import Path

from refresh_sentiment_daily import main as refresh_sentiment
from src.market_temperature import _last_complete_reference, _latest_overall_reference
from src.temperature_refresh import refresh_latest_sources
from src.temperature_store import load_observations


LATEST = Path(__file__).resolve().parent / 'data' / 'temperature' / 'latest'
SENTIMENT = ('a_breadth', 'a_newhigh_low_60', 'a_limit_balance')


def _sentiment_period():
    frame = load_observations(LATEST)
    rows = frame[frame['indicator_id'].isin(SENTIMENT)]
    return rows['data_period'].max() if not rows.empty else None


def main():
    previous_period = _sentiment_period()
    errors = []
    try:
        refresh_sentiment()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        errors.append(f'A股情绪：{error}')
    current_period = _sentiment_period()

    saved_count = 0
    try:
        refreshed = refresh_latest_sources(LATEST, include_ashare=True)
        saved_count = refreshed['saved_count']
        errors.extend(refreshed['errors'])
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        errors.append(f'其他市场来源：{error}')

    result, cutoff = _latest_overall_reference({})
    _last_complete_reference({}, (result, cutoff))
    report = dict(event='daily_market_temperature',
                  sentiment_period=current_period,
                  new_sentiment_period=current_period != previous_period,
                  other_observations_saved=saved_count,
                  cutoff=cutoff.isoformat(), coverage=result['coverage'],
                  score=result['internal_score'], label=result['label'],
                  missing=result['missing'], errors=errors)
    print(json.dumps(report, ensure_ascii=False, default=str), flush=True)
    if errors or result['internal_score'] is None:
        raise RuntimeError('每日市场温度更新仍有缺口；以上报告列出来源与覆盖情况')


if __name__ == '__main__':
    main()
