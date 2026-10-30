"""Automatic daily OHLCV history for individual-stock research."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAILY_CACHE_DIR = PROJECT_ROOT / "data" / "stock_daily"
DAILY_COLUMNS = ["交易日", "开盘", "最高", "最低", "收盘", "成交量", "成交额", "换手率"]


def _normalize_daily_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize AKShare's public A-share daily history fields."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    columns = {
        "日期": "交易日",
        "开盘": "开盘",
        "最高": "最高",
        "最低": "最低",
        "收盘": "收盘",
        "成交量": "成交量",
        "成交额": "成交额",
        "换手率": "换手率",
    }
    normalized = frame.rename(columns=columns).copy()
    if not {"交易日", "开盘", "最高", "最低", "收盘"}.issubset(normalized.columns):
        raise ValueError("行情源返回字段不完整，缺少日期或 OHLC 字段")
    for field in DAILY_COLUMNS:
        if field not in normalized:
            normalized[field] = pd.NA
    normalized["交易日"] = pd.to_datetime(normalized["交易日"], errors="coerce").dt.strftime("%Y-%m-%d")
    for field in DAILY_COLUMNS[1:]:
        normalized[field] = pd.to_numeric(normalized[field], errors="coerce")
    normalized = normalized.dropna(subset=["交易日", "开盘", "最高", "最低", "收盘"])
    normalized = normalized.drop_duplicates("交易日", keep="last").sort_values("交易日")
    return normalized[DAILY_COLUMNS].reset_index(drop=True)


def aggregate_stock_bars(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    """Compatibility bridge to the shared, source-free OHLCV model."""
    from .public_workspace.daily_model import aggregate_stock_bars as aggregate
    return aggregate(frame, period)


def _fetch_tencent_daily(code: str, start_date: date, end_date: date, adjustment: str) -> pd.DataFrame:
    """Fetch daily bars from Tencent's public A-share endpoint as a fallback."""
    market = "sh" if code.startswith(("600", "601", "603", "605", "688", "689", "900")) else "sz"
    symbol = f"{market}{code}"
    fq = "qfq" if adjustment == "前复权" else "none"
    rows = []
    segment_start = start_date
    while segment_start <= end_date:
        segment_end = min(segment_start + timedelta(days=364), end_date)
        params = {
            "_var": f"kline_day{fq}",
            "param": f"{symbol},day,{segment_start.isoformat()},{segment_end.isoformat()},1000,{fq}",
        }
        response = requests.get(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params=params,
            timeout=(5, 15),
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"},
        )
        response.raise_for_status()
        payload_text = response.text
        if "=" in payload_text and not payload_text.lstrip().startswith("{"):
            payload_text = payload_text.split("=", 1)[1]
        payload = json.loads(payload_text)
        stock_data = payload.get("data", {}).get(symbol, {})
        segment_rows = stock_data.get("qfqday" if fq == "qfq" else "day", [])
        if any(len(row) < 6 for row in segment_rows):
            raise ValueError("腾讯日线接口返回了不完整的 K 线记录")
        rows.extend(segment_rows)
        segment_start = segment_end + timedelta(days=1)
    if not rows:
        raise ValueError("腾讯日线接口未返回所需复权口径的数据")
    bar_rows = [row[:6] for row in rows]
    return pd.DataFrame(bar_rows, columns=["交易日", "开盘", "收盘", "最高", "最低", "成交量"])


def load_stock_daily_history(
    code: str,
    adjustment: str = "前复权",
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, dict, str | None]:
    """Load a local cache and automatically refresh it at most once per day."""
    normalized_code = str(code).strip().removesuffix(".0").zfill(6)
    if not normalized_code.isdigit() or len(normalized_code) != 6:
        raise ValueError("股票代码格式不正确")
    adjust_code = "qfq" if adjustment == "前复权" else ""
    cache_tag = adjust_code or "unadjusted"
    cache_path = DAILY_CACHE_DIR / f"{normalized_code}_{cache_tag}.csv"
    metadata_path = DAILY_CACHE_DIR / f"{normalized_code}_{cache_tag}.json"

    cached = pd.DataFrame(columns=DAILY_COLUMNS)
    metadata: dict = {}
    if cache_path.exists():
        try:
            cached = _normalize_daily_bars(pd.read_csv(cache_path, dtype={"交易日": str}))
        except (OSError, ValueError, pd.errors.ParserError):
            cached = pd.DataFrame(columns=DAILY_COLUMNS)
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}

    refreshed_today = metadata.get("refreshed_on") == date.today().isoformat()
    if not force_refresh and refreshed_today and not cached.empty:
        return cached, metadata, None

    start_date = date.today() - timedelta(days=365 * 3)
    end_date = date.today()
    provider_error = None
    source = "AKShare（东方财富公开日线源）"
    try:
        import akshare as ak

        provider_data = ak.stock_zh_a_hist(
            symbol=normalized_code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust=adjust_code,
        )
        bars = _normalize_daily_bars(provider_data)
        if bars.empty:
            raise ValueError("数据源没有返回该股票的日线记录")
    except Exception as exc:
        provider_error = f"AKShare: {str(exc)[:160]}"
        try:
            provider_data = _fetch_tencent_daily(normalized_code, start_date, end_date, adjustment)
            bars = _normalize_daily_bars(provider_data)
            if bars.empty:
                raise ValueError("数据源没有返回该股票的日线记录")
            source = "腾讯财经公开日线"
        except Exception as fallback_exc:
            combined_error = f"{provider_error}; 腾讯: {str(fallback_exc)[:160]}"
            if not cached.empty:
                return cached, metadata, combined_error[:320]
            return pd.DataFrame(columns=DAILY_COLUMNS), metadata, combined_error[:320]

    try:
        DAILY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        metadata = {
            "source": source,
            "adjustment": adjustment,
            "refreshed_on": date.today().isoformat(),
            "fetched_at": datetime.now().astimezone().isoformat(timespec="minutes"),
            "last_trade_date": bars.iloc[-1]["交易日"],
            "first_trade_date": bars.iloc[0]["交易日"],
        }
        temp_csv = cache_path.with_name(f"{cache_path.name}.tmp")
        temp_json = metadata_path.with_name(f"{metadata_path.name}.tmp")
        bars.to_csv(temp_csv, index=False, encoding="utf-8-sig")
        temp_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_csv.replace(cache_path)
        temp_json.replace(metadata_path)
        return bars, metadata, None
    except Exception as exc:
        if not cached.empty:
            return cached, metadata, str(exc)[:240]
        return pd.DataFrame(columns=DAILY_COLUMNS), metadata, str(exc)[:240]

