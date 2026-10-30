"""Original daily-to-week/month OHLCV aggregation; no loading."""
import pandas as pd

DAILY_COLUMNS=["交易日","开盘","最高","最低","收盘","成交量","成交额","换手率"]


def aggregate_stock_bars(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    """Aggregate real daily bars into weekly or monthly OHLCV candles."""
    if period == "日K":
        return frame.copy()
    frequencies = {"周K": "W-FRI", "月K": "M"}
    if period not in frequencies:
        raise ValueError("K 线周期必须是日K、周K或月K")
    if frame.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)

    grouped = frame.copy()
    dates = pd.to_datetime(grouped["交易日"], errors="coerce")
    grouped = grouped.loc[dates.notna()].copy()
    grouped["_period"] = dates.loc[dates.notna()].dt.to_period(frequencies[period])
    result = grouped.groupby("_period", sort=True).agg(
        交易日=("交易日", "last"),
        开盘=("开盘", "first"),
        最高=("最高", "max"),
        最低=("最低", "min"),
        收盘=("收盘", "last"),
        成交量=("成交量", lambda values: values.sum(min_count=1)),
        成交额=("成交额", lambda values: values.sum(min_count=1)),
    ).reset_index(drop=True)
    result["换手率"] = pd.NA
    return result[DAILY_COLUMNS]

