"""Local-first A-share daily market brief retrieval and formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
from typing import Callable
from urllib.request import Request, urlopen

import pandas as pd

from src.importers import infer_import_date, load_latest_research


_INDEX_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=1.000001,0.399001,0.399006,1.000688&fields=f12,f14,f2,f3,f4,f5,f6"
_BACKUP_INDEX_URL = "https://qt.gtimg.cn/q=s_sh000001,s_sz399001,s_sz399006,s_sh000688"
_INDEX_LABELS = ("上证指数", "深证成指", "创业板指", "科创50")


@dataclass(frozen=True)
class AshareIndexQuote:
    label: str
    price: float | None
    change: float | None
    change_percent: float | None


@dataclass(frozen=True)
class AshareDailyBrief:
    source: str
    snapshot_date: str
    indices: tuple[AshareIndexQuote, ...]
    total_volume: float | None
    total_amount: float | None
    is_trading_day: bool = True


def _fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; FeishuMarketBrief/1.0)"})
    with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed public HTTPS endpoint
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; FeishuMarketBrief/1.0)"})
    with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed public HTTPS endpoint
        return response.read().decode("gbk", errors="replace")


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if pd.notna(parsed) else None


class AshareMarketBriefService:
    def __init__(self, snapshot_directory: Path, fetch_json: Callable[[str], dict] = _fetch_json, fetch_text: Callable[[str], str] = _fetch_text, today: Callable[[], date] = date.today) -> None:
        self._snapshot_directory = snapshot_directory
        self._fetch_json = fetch_json
        self._fetch_text = fetch_text
        self._today = today

    def _local_brief(self) -> AshareDailyBrief | None:
        try:
            snapshot = load_latest_research(str(self._snapshot_directory))
        except (OSError, ValueError, pd.errors.ParserError):
            return None
        if snapshot is None or snapshot.empty:
            return None
        snapshot_date = infer_import_date(snapshot)
        if snapshot_date != self._today().isoformat():
            return None
        volume = pd.to_numeric(snapshot.get("成交量"), errors="coerce").sum() if "成交量" in snapshot else None
        amount = pd.to_numeric(snapshot.get("成交额"), errors="coerce").sum() if "成交额" in snapshot else None
        return AshareDailyBrief("本地快照", snapshot_date, (), float(volume) if volume is not None and pd.notna(volume) else None, float(amount) if amount is not None and pd.notna(amount) else None)

    def _public_brief(self) -> AshareDailyBrief:
        rows: list[dict] = []
        for _ in range(2):
            try:
                candidate = self._fetch_json(_INDEX_URL).get("data", {}).get("diff", [])
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                candidate = []
            if candidate:
                rows = [row for row in candidate if isinstance(row, dict)]
                break
        by_label = {str(row.get("f14", "")): row for row in rows if isinstance(row, dict)}
        indices = tuple(
            AshareIndexQuote(label, _number(by_label.get(label, {}).get("f2")), _number(by_label.get(label, {}).get("f4")), _number(by_label.get(label, {}).get("f3")))
            for label in _INDEX_LABELS
        )
        total_volume = sum(item for item in (_number(row.get("f5")) for row in rows if isinstance(row, dict)) if item is not None) or None
        total_amount = sum(item for item in (_number(row.get("f6")) for row in rows if isinstance(row, dict)) if item is not None) or None
        return AshareDailyBrief("公开行情", self._today().isoformat(), indices, total_volume, total_amount)

    def _backup_brief(self) -> AshareDailyBrief:
        try:
            payload = self._fetch_text(_BACKUP_INDEX_URL)
        except (OSError, ValueError, TypeError, UnicodeError):
            payload = ""
        quotes: dict[str, AshareIndexQuote] = {}
        for match in re.finditer(r'v_[^=]+="([^"]+)";', payload):
            fields = match.group(1).split("~")
            if len(fields) < 8 or fields[1] not in _INDEX_LABELS:
                continue
            quotes[fields[1]] = AshareIndexQuote(fields[1], _number(fields[3]), _number(fields[4]), _number(fields[5]))
        indices = tuple(quotes.get(label, AshareIndexQuote(label, None, None, None)) for label in _INDEX_LABELS)
        return AshareDailyBrief("备用公开行情", self._today().isoformat(), indices, None, None)

    def fetch_daily_brief(self) -> AshareDailyBrief:
        if self._today().weekday() >= 5:
            return AshareDailyBrief("非交易日", self._today().isoformat(), (), None, None, False)
        local = self._local_brief()
        if local:
            return local
        public = self._public_brief()
        return public if any(item.price is not None for item in public.indices) else self._backup_brief()


def _display_number(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None else "获取失败"


def format_ashare_daily_brief(brief: AshareDailyBrief) -> str:
    if not brief.is_trading_day:
        return "📊 A股当日复盘\n今日为非交易日，暂无当日行情。\n\n仅供研究参考，不构成投资建议。"
    lines = ["📊 A股当日复盘", f"数据时间：{brief.snapshot_date}｜来源：{brief.source}", "", "四大指数"]
    for item in brief.indices:
        if item.price is None:
            lines.append(f"• {item.label}：获取失败")
        else:
            marker = "🟢" if (item.change or 0) >= 0 else "🔴"
            lines.append(f"• {item.label}：{item.price:,.2f} {marker} ({item.change or 0:+.2f} / {item.change_percent or 0:+.2f}%)")
    if not brief.indices:
        lines.append("• 指数：本地快照未包含指数数据")
    lines.extend(
        (
            "",
            "市场活跃度",
            f"• 两市成交量：{_display_number(brief.total_volume)}",
            f"• 两市成交额：{_display_number(brief.total_amount)}",
            "• 市场宽度：获取失败",
            "• 涨停/跌停：获取失败",
            "• 板块强弱：获取失败",
            "",
            "仅供研究参考，不构成投资建议。",
        )
    )
    return "\n".join(lines)
