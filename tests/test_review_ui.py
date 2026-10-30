from streamlit.testing.v1 import AppTest


def review_app():
    import pandas as pd
    from src.pages_review import render_market_snapshot_comparison
    history = pd.DataFrame([
        {"快照日期": "2026-09-27", "代码": "000001", "名称": "样本", "价格": 10, "涨跌幅": 1, "成交额": 100},
        {"快照日期": "2026-09-28", "代码": "000002", "名称": "其他", "价格": 12, "涨跌幅": 2, "成交额": 120},
        {"快照日期": "2026-09-29", "代码": "000001", "名称": "样本", "价格": 11, "涨跌幅": 3, "成交额": 200},
        {"快照日期": "2026-09-30", "代码": "000001", "名称": "样本", "价格": 15, "涨跌幅": 5, "成交额": 300},
    ])
    stocks = pd.DataFrame({"代码": ["000001"], "行业": ["半导体"]})
    render_market_snapshot_comparison({"market_history": history, "stocks": stocks, "import_date": "2026-09-29", "stock_quote_source": "imported"})


def test_comparison_can_choose_older_overlap_without_future_data():
    app = AppTest.from_function(review_app).run()
    assert not app.exception
    assert app.selectbox(key="overview_compare_baseline").options == ["2026-09-28", "2026-09-27"]
    app.selectbox(key="overview_compare_baseline").set_value("2026-09-27").run()
    assert not app.exception
    assert app.metric[0].value == "1"
    app.segmented_control(key="overview_compare_sort").set_value("成交额倍数").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    assert {button.key for button in app.get("download_button")} >= {"overview_compare_export", "overview_compare_summary"}


def stock_review_app():
    import pandas as pd
    from src.pages_review import render_stock_snapshot_comparison
    render_stock_snapshot_comparison(pd.DataFrame([
        {"交易日": "2026-09-28", "价格": 10, "涨跌幅": 1, "成交额": 0},
        {"交易日": "2026-09-29", "价格": 11, "涨跌幅": 3, "成交额": 100},
    ]), "000001")


def test_stock_review_metrics_keep_unknown_amount_ratio():
    app = AppTest.from_function(stock_review_app).run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["+10.00%", "+2.00 个百分点", "—"]


def test_review_search_and_direction_filter_show_empty_safely():
    app = AppTest.from_function(review_app).run()
    app.selectbox(key="overview_compare_baseline").set_value("2026-09-27").run()
    app.text_input(key="overview_compare_search").set_value("000001").run()
    assert len(app.dataframe[0].value) == 1
    app.segmented_control(key="overview_compare_movement").set_value("涨幅走弱").run()
    assert not app.exception
    assert any("没有符合" in item.value for item in app.info)
    app.segmented_control(key="overview_compare_movement").set_value("全部").run()
    app.text_input(key="overview_compare_search").set_value("不存在").run()
    assert not app.exception
    assert any("没有符合" in item.value for item in app.info)


def test_review_industry_filter_routes_cloud_context():
    app = AppTest.from_function(review_app).run()
    app.selectbox(key="overview_compare_baseline").set_value("2026-09-27").run()
    app.selectbox(key="overview_compare_industry").set_value("半导体").run()
    assert len(app.dataframe[0].value) == 1
    app.button(key="overview_compare_open_cloud").click().run()
    assert not app.exception
    assert app.session_state["active_nav"] == "大盘云图"
    assert app.session_state["research_context"]["industry"] == "半导体"


def test_reset_review_filters_keeps_baseline_and_restores_results():
    app = AppTest.from_function(review_app).run()
    app.selectbox(key="overview_compare_baseline").set_value("2026-09-27").run()
    app.text_input(key="overview_compare_search").set_value("不存在").run()
    app.button(key="overview_compare_reset").click().run()
    assert not app.exception
    assert app.selectbox(key="overview_compare_baseline").value == "2026-09-27"
    assert app.text_input(key="overview_compare_search").value == ""
    assert app.segmented_control(key="overview_compare_movement").value == "全部"
    assert len(app.dataframe[0].value) == 1


def large_review_app():
    import pandas as pd
    from src.pages_review import render_market_snapshot_comparison
    rows = [{"快照日期": date, "代码": f"{code:06d}", "名称": f"样本{code}", "价格": 10, "涨跌幅": code if date.endswith("29") else 0, "成交额": 100}
            for date in ["2026-09-28", "2026-09-29"] for code in range(1, 66)]
    render_market_snapshot_comparison({"market_history": pd.DataFrame(rows), "import_date": "2026-09-29", "stock_quote_source": "imported"})


def test_review_paging_exposes_remaining_rows_and_clamps_after_search():
    app = AppTest.from_function(large_review_app).run(timeout=20)
    assert len(app.dataframe[0].value) == 50
    app.number_input(key="overview_compare_page").set_value(2).run()
    assert len(app.dataframe[0].value) == 15
    assert app.dataframe[0].value.iloc[0]["代码"] == "000015"
    assert len(app.selectbox(key="overview_compare_stock").options) == 15
    app.text_input(key="overview_compare_search").set_value("000065").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    assert app.number_input(key="overview_compare_page").value == 1


def toggle_review_app():
    import streamlit as st
    import pandas as pd
    from src.pages_review import render_market_snapshot_comparison
    show = st.checkbox("显示复盘", value=True, key="show_review")
    if show:
        history = pd.DataFrame([{"快照日期": date, "代码": "000001", "名称": "样本", "涨跌幅": 1, "成交额": 100}
                                for date in ["2026-09-28", "2026-09-29"]])
        render_market_snapshot_comparison({"market_history": history, "import_date": "2026-09-29", "stock_quote_source": "imported"})


def test_review_preserves_search_when_temporarily_not_rendered():
    app = AppTest.from_function(toggle_review_app).run()
    app.text_input(key="overview_compare_search").set_value("000001").run()
    app.checkbox(key="show_review").uncheck().run()
    app.checkbox(key="show_review").check().run()
    assert not app.exception
    assert app.text_input(key="overview_compare_search").value == "000001"


def test_review_shows_valid_amount_ratio_coverage():
    app = AppTest.from_function(large_review_app).run()
    assert any("成交额倍数有效样本 65 / 65" in item.value for item in app.caption)


def test_industry_board_aggregates_and_routes_selected_industry():
    app = AppTest.from_function(review_app).run()
    app.selectbox(key="overview_compare_baseline").set_value("2026-09-27").run()
    board = next(table.value for table in app.dataframe if "共同样本" in table.value.columns)
    assert board.iloc[0]["行业"] == "半导体"
    assert board.iloc[0]["平均涨幅变化"] == 2
    app.button(key="review_industry_open_cloud").click().run()
    assert not app.exception
    assert app.session_state["research_context"]["industry"] == "半导体"


def test_industry_minimum_sample_filter_does_not_break_empty_board():
    app = AppTest.from_function(review_app).run()
    app.selectbox(key="overview_compare_baseline").set_value("2026-09-27").run()
    app.number_input(key="review_industry_minimum").set_value(2).run()
    assert not app.exception
    assert any("样本门槛" in item.value for item in app.info)
    app.number_input(key="review_industry_minimum").set_value(1).run()
    assert not app.exception
    assert any("共同样本" in table.value.columns for table in app.dataframe)


def industry_board_app():
    import pandas as pd
    from src.pages_review import render_industry_comparison_board
    from src.snapshot_review import industry_snapshot_comparison
    components = pd.DataFrame({"行业": ["电子", "通信"], "代码": ["000001", "000002"], "名称": ["甲", "乙"],
                               "涨跌幅变化": [2, -3], "成交额_当前": [200, 50], "成交额_对照": [100, 100]})
    render_industry_comparison_board(industry_snapshot_comparison(components), "2026-09-29", "2026-09-28", components)


def test_industry_low_first_order_and_component_detail_route():
    app = AppTest.from_function(industry_board_app).run()
    app.segmented_control(key="review_industry_direction").set_value("从低到高").run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]["行业"] == "通信"
    app.selectbox(key="review_industry_selection").set_value("通信").run()
    assert app.selectbox(key="review_industry_stock").options == ["000002 · 乙"]
    app.button(key="review_industry_open_stock").click().run()
    assert not app.exception
    assert app.session_state["stock_detail_query"] == "000002"
    assert app.session_state["active_nav"] == "个股详情"


def test_selected_industry_exposes_component_and_summary_exports():
    app = AppTest.from_function(industry_board_app).run()
    app.selectbox(key="review_industry_selection").set_value("通信").run()
    assert not app.exception
    assert {button.key for button in app.get("download_button")} >= {"review_industry_components_export", "review_industry_summary_export"}


def test_industry_view_ignores_empty_stock_search():
    app = AppTest.from_function(review_app).run()
    app.selectbox(key="overview_compare_baseline").set_value("2026-09-27").run()
    app.text_input(key="overview_compare_search").set_value("不存在").run()
    app.segmented_control(key="overview_compare_view").set_value("行业变化").run()
    assert not app.exception
    assert any("共同样本" in table.value.columns for table in app.dataframe)
    assert app.selectbox(key="review_industry_selection").value == "半导体"
    app.segmented_control(key="overview_compare_view").set_value("个股变化").run()
    assert app.text_input(key="overview_compare_search").value == "不存在"
    assert any("没有符合" in item.value for item in app.info)


def test_industry_view_without_classification_keeps_stock_view_available():
    app = AppTest.from_function(large_review_app).run()
    app.segmented_control(key="overview_compare_view").set_value("行业变化").run()
    assert not app.exception
    assert any("缺少行业分类" in item.value for item in app.info)
    app.segmented_control(key="overview_compare_view").set_value("个股变化").run()
    assert len(app.dataframe[0].value) == 50


def test_industry_component_preview_shows_only_selected_common_stock():
    app = AppTest.from_function(industry_board_app).run()
    app.selectbox(key="review_industry_selection").set_value("通信").run()
    previews = [table.value for table in app.dataframe if "代码" in table.value.columns]
    assert len(previews) == 1
    assert previews[0]["代码"].tolist() == ["000002"]


def test_comparison_reports_coverage_against_both_imported_samples():
    app = AppTest.from_function(large_review_app).run()
    assert any("共同样本占当前快照 100.0%，占对照快照 100.0%" in item.value for item in app.caption)


def stock_history_review_app():
    import pandas as pd
    from src.pages_review import render_stock_snapshot_comparison
    history = pd.DataFrame({"交易日": ["2026-09-25", "2026-09-28", "2026-09-29"],
                            "价格": [10, 11, 12], "涨跌幅": [1, 2, 3], "成交额": [100, 150, 200]})
    render_stock_snapshot_comparison(history, "000001")


def test_stock_history_can_compare_older_saved_date():
    app = AppTest.from_function(stock_history_review_app).run()
    app.selectbox(key="detail_compare_baseline_000001").set_value("2026-09-25").run()
    assert not app.exception
    assert app.metric[0].value == "+20.00%"
    assert app.metric[1].value == "+2.00 个百分点"
    assert app.metric[2].value == "2.00 倍"
    assert len(app.dataframe[0].value) == 2
    assert any(button.key == "detail_compare_export_000001" for button in app.get("download_button"))


def switching_stock_review_app():
    import pandas as pd
    import streamlit as st
    from src.pages_review import render_stock_snapshot_comparison
    code = st.selectbox("切换个股", ["000001", "000002"], key="test_stock_switch")
    history = pd.DataFrame({"交易日": ["2026-09-25", "2026-09-28", "2026-09-29"],
                            "价格": [10, 11, 12], "涨跌幅": [1, 2, 3]})
    render_stock_snapshot_comparison(history, code)


def test_stock_baseline_is_isolated_per_code_and_missing_amount_stays_unknown():
    app = AppTest.from_function(switching_stock_review_app).run()
    app.selectbox(key="detail_compare_baseline_000001").set_value("2026-09-25").run()
    app.selectbox(key="test_stock_switch").set_value("000002").run()
    assert app.selectbox(key="detail_compare_baseline_000002").value == "2026-09-28"
    assert app.metric[2].value == "—"
    assert app.dataframe[0].value["成交额"].isna().all()
    app.selectbox(key="test_stock_switch").set_value("000001").run()
    assert not app.exception
    assert app.selectbox(key="detail_compare_baseline_000001").value == "2026-09-25"
