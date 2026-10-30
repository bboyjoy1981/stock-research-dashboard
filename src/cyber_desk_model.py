"""Read-only view model for the personal cyber trading desk."""

from __future__ import annotations

import math

import pandas as pd


def _code(value: object) -> str:
    raw = str(value).strip().removesuffix(".0")
    return raw.zfill(6) if raw.isdigit() else raw


def _number(value: object, *, positive: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (positive and number <= 0):
        return None
    return number


def _label(*values: object, fallback: str) -> str:
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return fallback


def build_cyber_desk_model(data: dict) -> dict:
    """Keep imported watchlist identity separate from quote snapshot coverage."""
    watchlist_codes = list(dict.fromkeys(_code(code) for code in data.get("watchlist_codes", []) if str(code).strip()))
    if not watchlist_codes:
        return {"mode": "empty", "source": "未添加关注股票", "snapshot_date": None, "stocks": [], "sectors": []}
    pool = data.get("research_pool")
    if not isinstance(pool, pd.DataFrame) or not {"代码", "名称"}.issubset(pool.columns):
        pool = pd.DataFrame(columns=["代码", "名称"])

    imported_quotes = data.get("stock_quote_source") == "imported" and bool(data.get("import_date"))
    quotes = data.get("stocks")
    quote_map: dict[str, dict] = {}
    if imported_quotes and isinstance(quotes, pd.DataFrame) and "代码" in quotes:
        for row in quotes.drop_duplicates("代码", keep="last").to_dict("records"):
            quote_map[_code(row.get("代码"))] = row

    stocks_by_code = {}
    seen = set()
    for row in pool.to_dict("records"):
        code = _code(row.get("代码", ""))
        if not code or code in seen or code not in watchlist_codes:
            continue
        seen.add(code)
        quote = quote_map.get(code, {})
        sector = _label(row.get("细分行业"), row.get("行业"), row.get("板块"), fallback="未分类")
        stocks_by_code[code] = {
            "code": code,
            "name": _label(row.get("名称"), fallback=code),
            "sector": sector,
            "price": _number(quote.get("价格"), positive=True),
            "change_pct": _number(quote.get("涨跌幅")),
            "volume": _number(quote.get("成交量")),
            "amount_yuan": _number(quote.get("成交额")),
            "turnover_pct": _number(quote.get("换手率")),
            "volume_ratio": _number(quote.get("量比")),
            "volume_source": str(quote.get("成交量源字段") or "").strip(),
        }

    stocks = [stocks_by_code.get(code, {
        "code": code, "name": code, "sector": "未分类", "price": None, "change_pct": None,
        "volume": None, "amount_yuan": None, "turnover_pct": None,
        "volume_ratio": None, "volume_source": "",
    }) for code in watchlist_codes]

    sectors = sorted({stock["sector"] for stock in stocks if stock["sector"] != "未分类"})
    return {
        "mode": "snapshot" if imported_quotes else "watchlist_only",
        "source": "导入行情快照" if imported_quotes else "导入关注名单",
        "snapshot_date": str(data["import_date"]) if imported_quotes else None,
        "stocks": stocks,
        "sectors": sectors,
    }
