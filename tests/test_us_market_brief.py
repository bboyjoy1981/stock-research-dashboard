import math

import pytest

import src.us_market_brief as market_brief
from src.us_market_brief import MarketQuote, UsMarketBriefService, format_us_market_brief


def test_fetch_chart_uses_a_browser_user_agent(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"chart": {"result": []}}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(market_brief, "urlopen", fake_urlopen)

    assert market_brief._fetch_chart("^NDX", 3.0) == {"chart": {"result": []}}
    assert captured["request"].get_header("User-agent")
    assert captured["timeout"] == 3.0


def test_fetch_quotes_uses_last_two_valid_closes_to_calculate_change():
    def fetch(_symbol):
        return {"chart": {"result": [{"indicators": {"quote": [{"close": [None, 100.0, 101.5]}]}}]}}

    quote = UsMarketBriefService(fetch=fetch).fetch_quotes()[0]

    assert quote.price == 101.5
    assert quote.change == 1.5
    assert quote.change_percent == pytest.approx(1.5)


def test_fetch_quotes_returns_none_when_chart_has_insufficient_valid_closes():
    def fetch(_symbol):
        return {"chart": {"result": [{"indicators": {"quote": [{"close": [None, 101.5]}]}}]}}

    assert UsMarketBriefService(fetch=fetch).fetch_quotes()[0] is None


def test_fetch_quotes_ignores_non_finite_closes():
    def fetch(_symbol):
        return {"chart": {"result": [{"indicators": {"quote": [{"close": [100.0, math.nan]}]}}]}}

    assert UsMarketBriefService(fetch=fetch).fetch_quotes()[0] is None


def test_format_us_market_brief_groups_quotes_and_marks_extremes():
    quotes = [MarketQuote(symbol, label, 100.0, change, change) for symbol, label, change in (
        ("^NDX", "纳斯达克 100", 1.0), ("^DJI", "道琼斯", -1.0), ("^GSPC", "标普 500", 0.0),
        ("NVDA", "英伟达 NVDA", 3.0), ("INTC", "英特尔 INTC", -2.0), ("MU", "美光科技 MU", 1.0),
        ("RKLB", "Rocket Lab RKLB", 0.5), ("WDC", "西部数据 WDC", -0.5),
        ("PGJ", "金龙中国 PGJ", 0.1), ("GC=F", "黄金", 0.2), ("CL=F", "原油", -0.2),
    )]
    text = format_us_market_brief(quotes)
    assert "三大指数" in text and "热门科技股" in text and "中概股" in text and "商品" in text
    assert "最大涨幅" in text and "最大跌幅" in text
    assert "仅供研究参考，不构成投资建议。" in text


def test_format_us_market_brief_shows_single_failure_and_all_failure_message():
    quotes = [None] + [MarketQuote(symbol, label, 100.0, 1.0, 1.0) for symbol, label in [("^DJI", "道琼斯"), ("^GSPC", "标普 500"), ("NVDA", "英伟达 NVDA"), ("INTC", "英特尔 INTC"), ("MU", "美光科技 MU"), ("RKLB", "Rocket Lab RKLB"), ("WDC", "西部数据 WDC"), ("PGJ", "金龙中国 PGJ"), ("GC=F", "黄金"), ("CL=F", "原油")]]
    assert "获取失败" in format_us_market_brief(quotes)
    assert format_us_market_brief([None] * 11) == "行情数据暂不可用，请稍后重试。"
