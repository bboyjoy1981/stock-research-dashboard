"""Fast, fixed-symbol US market brief retrieval and formatting."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import math
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen


MARKET_GROUPS = (
    ("三大指数", (("^NDX", "纳斯达克 100"), ("^DJI", "道琼斯"), ("^GSPC", "标普 500"))),
    ("热门科技股", (("NVDA", "英伟达 NVDA"), ("INTC", "英特尔 INTC"), ("MU", "美光科技 MU"), ("RKLB", "Rocket Lab RKLB"), ("WDC", "西部数据 WDC"))),
    ("中概股", (("PGJ", "金龙中国 PGJ"),)),
    ("商品", (("GC=F", "黄金"), ("CL=F", "原油"))),
)
_SYMBOLS = tuple(item for _, group in MARKET_GROUPS for item in group)


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    label: str
    price: float
    change: float
    change_percent: float


def _fetch_chart(symbol: str, timeout_seconds: float) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?interval=1d&range=5d"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; FeishuMarketBrief/1.0)"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed HTTPS endpoint
        return json.loads(response.read().decode("utf-8"))


class UsMarketBriefService:
    def __init__(self, fetch: Callable[[str], dict] | None = None, timeout_seconds: float = 5.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._fetch = fetch or (lambda symbol: _fetch_chart(symbol, timeout_seconds))

    def _quote(self, symbol: str, label: str) -> MarketQuote | None:
        try:
            closes = self._fetch(symbol)["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            valid = [close for value in closes if value is not None and math.isfinite(close := float(value))]
            if len(valid) < 2 or valid[-2] == 0:
                return None
            change = valid[-1] - valid[-2]
            return MarketQuote(symbol, label, valid[-1], change, change / valid[-2] * 100)
        except (KeyError, IndexError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return None

    def fetch_quotes(self) -> list[MarketQuote | None]:
        with ThreadPoolExecutor(max_workers=len(_SYMBOLS)) as pool:
            return list(pool.map(lambda item: self._quote(*item), _SYMBOLS))


def format_us_market_brief(quotes: list[MarketQuote | None]) -> str:
    if not any(quotes):
        return "行情数据暂不可用，请稍后重试。"
    by_symbol = {symbol: item for (symbol, _), item in zip(_SYMBOLS, quotes)}
    technology = [by_symbol[symbol] for symbol, _ in MARKET_GROUPS[1][1] if by_symbol.get(symbol)]
    largest_gain = max(technology, key=lambda item: item.change_percent) if technology else None
    largest_loss = min(technology, key=lambda item: item.change_percent) if technology else None
    lines = ["📊 美股隔夜收盘"]
    for group, symbols in MARKET_GROUPS:
        lines.extend(("", group))
        for symbol, label in symbols:
            item = by_symbol.get(symbol)
            if item is None:
                lines.append(f"• {label}：获取失败")
                continue
            marker = "🟢" if item.change >= 0 else "🔴"
            suffix = ""
            if group == "热门科技股" and item == largest_gain:
                suffix = "  最大涨幅"
            elif group == "热门科技股" and item == largest_loss:
                suffix = "  最大跌幅"
            lines.append(f"• {label}：{item.price:,.2f} {marker} ({item.change:+.2f} / {item.change_percent:+.2f}%){suffix}")
    lines.extend(("", "仅供研究参考，不构成投资建议。"))
    return "\n".join(lines)
