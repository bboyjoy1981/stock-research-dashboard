"""Recent A-share minute prices for the focused watchlist stock."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "stock_minute"
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_COLUMNS = ["时间", "收盘", "成交量"]


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=_COLUMNS)
    normalized = frame.rename(columns={
        "day": "时间", "close": "收盘", "volume": "成交量",
    }).copy()
    if not {"时间", "收盘"}.issubset(normalized.columns):
        raise ValueError("分钟行情缺少时间或收盘价")
    if "成交量" not in normalized:
        normalized["成交量"] = pd.NA
    normalized["时间"] = pd.to_datetime(normalized["时间"], errors="coerce")
    normalized["收盘"] = pd.to_numeric(normalized["收盘"], errors="coerce")
    normalized["成交量"] = pd.to_numeric(normalized["成交量"], errors="coerce")
    normalized = normalized.dropna(subset=["时间", "收盘"])
    normalized = normalized.loc[normalized["收盘"].gt(0)].copy()
    minute = normalized["时间"].dt.hour * 60 + normalized["时间"].dt.minute
    session = minute.between(570, 690) | minute.between(780, 900)
    normalized = normalized.loc[session].drop_duplicates("时间", keep="last")
    return normalized.sort_values("时间")[_COLUMNS].reset_index(drop=True)


def _market_open(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    current = now.time()
    return time(9, 30) <= current <= time(11, 30) or time(13) <= current <= time(15)


def _source_symbol(code: str) -> str:
    if code.startswith(("600", "601", "603", "605", "688", "689", "900")):
        return f"sh{code}"
    if code.startswith(("4", "8", "9")):
        return f"bj{code}"
    return f"sz{code}"


def _fetch_minutes(code: str) -> tuple[pd.DataFrame, str]:
    import akshare as ak

    try:
        frame = _normalize(ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust=""))
        if frame.empty:
            raise ValueError("东方财富未返回有效分钟记录")
        return frame, "AKShare（东方财富公开分钟行情）"
    except Exception as eastmoney_error:
        try:
            frame = _normalize(ak.stock_zh_a_minute(symbol=_source_symbol(code), period="1", adjust=""))
            if frame.empty:
                raise ValueError("新浪未返回有效分钟记录")
            return frame, "AKShare（新浪公开分钟行情）"
        except Exception as sina_error:
            raise RuntimeError(
                f"东方财富：{str(eastmoney_error)[:120]}；新浪：{str(sina_error)[:120]}"
            ) from sina_error


def load_stock_minutes(code: str, force_refresh: bool = False) -> tuple[pd.DataFrame, dict, str | None]:
    """Refresh at most once a minute during trading, preserving the last saved day."""
    code = str(code).strip().removesuffix(".0").zfill(6)
    if not code.isdigit() or len(code) != 6:
        raise ValueError("股票代码格式不正确")
    now = datetime.now(_SHANGHAI)
    metadata_path = _CACHE_DIR / f"{code}.json"
    metadata: dict = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            metadata = {}
    files = sorted(_CACHE_DIR.glob(f"{code}_????????.csv"), reverse=True) if _CACHE_DIR.exists() else []
    cached = pd.DataFrame(columns=_COLUMNS)
    if files:
        try:
            cached = _normalize(pd.read_csv(files[0]))
        except (OSError, ValueError, pd.errors.ParserError):
            cached = pd.DataFrame(columns=_COLUMNS)
    last_fetch = pd.to_datetime(metadata.get("fetched_at"), errors="coerce", utc=True)
    recent = pd.notna(last_fetch) and (now - last_fetch.to_pydatetime().astimezone(_SHANGHAI)).total_seconds() < 60
    fetched_today = metadata.get("fetched_on") == now.date().isoformat()
    if not force_refresh and not cached.empty and fetched_today and (recent or not _market_open(now)):
        return cached, metadata, None
    last_attempt = pd.to_datetime(metadata.get("failed_at"), errors="coerce", utc=True)
    retry_after = 60 if _market_open(now) else 300
    failed_recently = pd.notna(last_attempt) and (
        0 <= (now - last_attempt.to_pydatetime().astimezone(_SHANGHAI)).total_seconds() < retry_after
    )
    if not force_refresh and failed_recently:
        return cached, metadata, metadata.get("last_error")

    try:
        frame, source = _fetch_minutes(code)
        latest_day = frame["时间"].dt.date.max()
        frame = frame.loc[frame["时间"].dt.date.eq(latest_day)].copy()
        if frame.empty:
            raise ValueError("数据源没有返回最近交易日的分钟行情")
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = _CACHE_DIR / f"{code}_{latest_day:%Y%m%d}.csv"
        temporary = target.with_suffix(".tmp")
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        temporary.replace(target)
        metadata = {
            "source": source,
            "trade_date": latest_day.isoformat(),
            "fetched_on": now.date().isoformat(),
            "fetched_at": now.isoformat(timespec="seconds"),
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return frame, metadata, None
    except Exception as exc:
        error = str(exc)[:280]
        metadata = {**metadata, "failed_at": now.isoformat(timespec="seconds"), "last_error": error}
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return cached, metadata, error


def minute_series(frame: pd.DataFrame, period: int) -> pd.DataFrame:
    """Aggregate actual 1-minute closes and volume into 5-minute endpoints."""
    if period not in (1, 5):
        raise ValueError("分钟周期必须是 1 或 5")
    if period == 1 or frame.empty:
        return frame.copy()
    indexed = frame.set_index("时间")
    grouped = indexed.resample("5min", closed="right", label="right").agg(
        收盘=("收盘", "last"), 成交量=("成交量", lambda values: values.sum(min_count=1)),
    )
    return grouped.dropna(subset=["收盘"]).reset_index()
