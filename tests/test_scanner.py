import pandas as pd
import pytest
from src.pages_scanner import filter_candidates
from src.calculations import stock_top_percent


def test_stock_top_percent_handles_ties_missing_values_and_single_sample():
    assert stock_top_percent(5, [5, 5, 1, None]) == pytest.approx(100 / 3)
    assert stock_top_percent(1, [5, 5, 1]) == 100
    assert stock_top_percent(5, [5]) == 100
    assert stock_top_percent(None, [5]) is None
    assert stock_top_percent(5, []) is None


def test_candidate_search_is_literal_and_does_not_match_missing_amount():
    stocks = pd.DataFrame({"代码": ["000001", "000002"], "名称": ["甲[测试]", "乙"], "涨跌幅": [3, 2], "成交额": [None, 2e8]})
    assert filter_candidates(stocks, query="[")["代码"].tolist() == ["000001"]
    assert filter_candidates(stocks, minimum_amount=1e8)["代码"].tolist() == ["000002"]


def test_candidate_risk_sort_is_low_first_and_group_filter_is_exact():
    stocks = pd.DataFrame({"代码": ["1", "2", "3"], "行业": ["电子", "电子", "电子设备"], "涨跌幅": [3, 2, 4], "风险分": [40, 10, 5]})
    result = filter_candidates(stocks, group_field="行业", group="电子", sort_field="风险分", ascending=True)
    assert result["代码"].tolist() == ["2", "1"]


def test_candidate_positive_amount_filter_requires_amount_field():
    stocks = pd.DataFrame({"代码": ["1"], "名称": ["甲"], "涨跌幅": [2]})
    assert filter_candidates(stocks, minimum_amount=1).empty


def test_candidate_review_report_preserves_scope_and_missing_scores():
    from src.pages_scanner import candidate_review_report
    report = candidate_review_report(
        date="2026-09-16", origin="导入行情快照", sample_count=5016,
        matched_count=120, displayed_count=50, query="PCB", market="科创板",
        group="电子", minimum_change=3, minimum_amount=1e8,
        sort_field="涨跌幅", minimum_score=None, maximum_risk=None,
    )
    assert "2026-09-16" in report
    assert "符合条件：120" in report and "卡片展示：50" in report
    assert "市场范围：科创板" in report and "搜索：PCB" in report
    assert "最低成交额：1.00 亿元" in report
    assert "综合分门槛：未启用" in report
    assert "不是实时行情" in report


@pytest.mark.parametrize("market,expected", [("沪市主板", ["600001"]), ("深市主板", ["000001"]), ("创业板", ["300001"]), ("科创板", ["688001"]), ("北交所", ["920001", "830001"])])
def test_candidate_market_scope_uses_code_group(market, expected):
    stocks = pd.DataFrame({"代码": ["600001", "000001", "300001", "688001", "920001", "830001"], "涨跌幅": [1] * 6})
    assert filter_candidates(stocks, market=market)["代码"].tolist() == expected


def scanner_presets_app():
    import pandas as pd
    from src.pages_scanner import render_candidate_workspace
    stocks = pd.DataFrame({"代码": ["600001", "300001"], "名称": ["甲", "乙"], "涨跌幅": [5, -2], "成交额": [2e8, 3e8], "价格": [10, 20]})
    render_candidate_workspace({"stocks": stocks, "import_date": "2026-09-29", "stock_quote_source": "imported"})


def test_scanner_presets_apply_thresholds_and_full_export_exists():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(scanner_presets_app).run(timeout=20)
    app.segmented_control(key="scanner_preset").set_value("强势动量").run()
    assert app.slider(key="scanner_min_change").value == 3
    assert app.number_input(key="scanner_min_amount").value == 1
    app.segmented_control(key="scanner_preset").set_value("成交活跃").run()
    assert app.slider(key="scanner_min_change").value == -30
    assert app.selectbox(key="scanner_sort_field").value == "成交额"
    assert not app.exception
    assert any(button.key == "scanner_export_full" for button in app.get("download_button"))


def test_candidate_quote_details_use_available_aliases_without_price_substitution():
    from src.pages_scanner import quote_detail_values
    details = quote_detail_values(pd.Series({"价格": 99, "昨收价": 10, "今开": 11, "最高价": 12, "最低": None}))
    assert details == {"昨收": "10.00", "今开": "11.00", "最高": "12.00", "最低": "—"}


def test_candidate_score_and_risk_thresholds_exclude_unknown_scores():
    stocks = pd.DataFrame({"代码": ["1", "2", "3"], "涨跌幅": [1, 1, 1], "综合分": [80, 70, None], "风险分": [20, 60, 10]})
    assert filter_candidates(stocks, minimum_score=60, maximum_risk=35)["代码"].tolist() == ["1"]
    assert filter_candidates(stocks.drop(columns="综合分"), minimum_score=60).empty


def test_candidate_pages_render_ten_cards_and_search_selection_moves_page():
    from streamlit.testing.v1 import AppTest

    def render():
        import pandas as pd
        from src.pages_scanner import render_candidate_workspace
        stocks = pd.DataFrame({"代码": [f"{number:06d}" for number in range(1, 32)], "名称": [f"公司{number}" for number in range(1, 32)], "板块": ["电子"] * 31, "涨跌幅": [1.0] * 31, "价格": [10.0] * 31})
        render_candidate_workspace({"stocks": stocks})

    app = AppTest.from_function(render).run(timeout=30)
    assert not app.exception
    assert len([button for button in app.button if str(button.key).startswith("scanner_candidate_")]) == 10
    target = app.selectbox(key="scanner_stock_jump").options[20]
    app.selectbox(key="scanner_stock_jump").select(target).run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="scanner_page").value == 3
    assert app.button(key="scanner_candidate_20").label == target
