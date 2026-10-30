"""Focused-stock public quote, cached independently from imported snapshots."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _number(value: object) -> float | None:
    result = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(result) else float(result)


def _market_open(now: datetime) -> bool:
    return now.weekday() < 5 and (time(9, 30) <= now.time() <= time(11, 30) or time(13) <= now.time() <= time(15))


@st.cache_data(ttl=60, max_entries=64, show_spinner=False)
def _fetch_quote(code: str) -> dict:
    import akshare as ak

    frame = ak.stock_bid_ask_em(symbol=code)
    if frame is None or frame.empty or not {"item", "value"}.issubset(frame.columns):
        raise ValueError("公开盘口接口没有返回可用字段")
    values = dict(zip(frame["item"].astype(str), frame["value"]))
    price = _number(values.get("最新"))
    if price is None or price <= 0:
        raise ValueError("公开盘口接口没有返回有效最新价")
    previous = _number(values.get("昨收"))
    change_pct = (price / previous - 1) * 100 if previous and previous > 0 else None
    return {
        "price": price, "change_pct": change_pct,
        "volume_hands": _number(values.get("总手")),
        "amount_yuan": _number(values.get("金额")),
        "turnover_pct": _number(values.get("换手")),
        "volume_ratio": _number(values.get("量比")),
        "fetched_at": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
    }


def load_focused_quote(code: str, *, force: bool = False) -> tuple[dict | None, str | None]:
    """Keep last success visibly stale after a failed refresh."""
    now = datetime.now(SHANGHAI)
    cache_key = f"cyber_last_quote_{code}"
    attempt_key = f"cyber_quote_attempt_{code}"
    last_attempt = st.session_state.get(attempt_key)
    interval = 60 if _market_open(now) else 300
    if not force and last_attempt and (now - last_attempt).total_seconds() < interval:
        return st.session_state.get(cache_key), st.session_state.get(f"{cache_key}_error")
    st.session_state[attempt_key] = now
    try:
        quote = _fetch_quote(code)
        st.session_state[cache_key] = quote
        st.session_state[f"{cache_key}_error"] = None
        return quote, None
    except Exception as exc:
        message = str(exc)[:180]
        st.session_state[f"{cache_key}_error"] = message
        return st.session_state.get(cache_key), message
