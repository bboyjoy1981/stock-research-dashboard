import pandas as pd


def test_close_brief_excludes_missing_returns_from_breadth_denominator():
    from src.close_brief import build_close_brief
    stocks = pd.DataFrame({"涨跌幅": [2, -1, None], "成交额": [1e8, None, 2e8]})
    report = build_close_brief(stocks, date="2026-09-16", origin="导入行情快照")
    assert "上涨占比：50.0%" in report
    assert "有效涨跌：2/3" in report
    assert "已提供成交额合计：3.00 亿元" in report
    assert "成交额覆盖：2/3" in report
    assert "2026-09-16" in report


def test_close_brief_without_valid_quotes_does_not_describe_market_direction():
    from src.close_brief import build_close_brief
    report = build_close_brief(pd.DataFrame({"涨跌幅": [None]}), date=None, origin="演示数据")
    assert "市场状态：数据不足" in report
    assert "平均涨跌：未提供" in report
    assert "已提供成交额合计：未提供" in report


def test_close_brief_does_not_label_turnover_as_capital_flow():
    from src.close_brief import build_close_brief
    report = build_close_brief(pd.DataFrame({"涨跌幅": [10], "成交额": [1e8]}), date="2026-09-16", origin="导入行情快照")
    assert "不代表资金净流入" in report
    assert "不等于确认涨跌停" in report
