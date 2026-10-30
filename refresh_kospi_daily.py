"""Capture completed KOSPI closes into the latest research observation store."""

from pathlib import Path

from src.overseas_temperature import collect_kospi_source
from src.temperature_store import load_observations, save_observations


def main() -> int:
    directory = Path(__file__).resolve().parent / 'data' / 'temperature' / 'latest'
    frame, status, error = collect_kospi_source()
    if error:
        print(error)
        return 1
    previous = load_observations(directory)
    existing = previous[previous['indicator_id'].eq('kospi')]
    prior_day = existing['data_period'].max() if not existing.empty else None
    latest_day = frame.iloc[-1]['data_period']
    if prior_day and latest_day < prior_day:
        print(f'KOSPI来源退回旧交易日：{latest_day}；库存最新：{prior_day}')
        return 1
    if prior_day == latest_day:
        print(f'KOSPI没有新收盘日：{latest_day}；保留原始记录')
        return 0
    save_observations(frame, directory)
    print(f"{status['说明']}；已保存到 {directory}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
