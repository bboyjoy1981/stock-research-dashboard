from streamlit.testing.v1 import AppTest
from pathlib import Path
from src.pages_public import market_quote_origin


def research_path_app():
    import streamlit as st
    from src.pages_public import _render_research_context
    st.session_state.setdefault("research_context", {"source": "大盘云图", "industry": "半导体"})
    st.session_state.setdefault("terminal_industry_query", "半导体")
    _render_research_context("probe")


def test_clear_research_path_also_clears_cloud_filter():
    app = AppTest.from_function(research_path_app).run(timeout=20)
    app.button(key="clear_research_context_probe").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["terminal_industry_query"] == ""


def test_cloud_full_market_reset_clears_quick_location_selection():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)
    group = app.selectbox(key="terminal_quick_group").options[1]
    app.selectbox(key="terminal_quick_group").select(group).run(timeout=30)
    app.button(key="terminal_quick_focus").click().run(timeout=30)
    app.button(key="terminal_quick_reset").click().run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="terminal_quick_group").value == "全市场"


def test_research_path_can_open_cloud_with_industry_focus():
    app = AppTest.from_function(research_path_app).run(timeout=20)
    app.button(key="research_path_cloud_probe").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["active_nav"] == "大盘云图"
    assert app.session_state["terminal_industry_query"] == "半导体"


def test_research_path_opens_peers_without_old_stock_search():
    app = AppTest.from_function(research_path_app)
    app.session_state["stock_detail_query"] = "300750"
    app.run(timeout=20)
    app.button(key="research_path_peers_probe").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["active_nav"] == "个股详情"
    assert app.session_state["stock_detail_query"] == ""
    assert app.session_state["research_context"]["industry"] == "半导体"


def test_stock_peer_board_precedes_secondary_research_sections():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)
    assert not app.exception
    headings = [item.value for item in app.subheader]
    assert headings.index("同类对比") < headings.index("研究画像")
    assert headings.index("同类对比") < headings.index("盘后复盘要点")


def index_preview_app():
    import pandas as pd
    from src.pages_public import render_demo_index_preview
    render_demo_index_preview(pd.DataFrame({"名称": ["示例指数"], "点位": [1234.5], "涨跌幅": [1.2]}))


def test_demo_indices_require_explicit_opt_in_and_keep_source_label():
    app = AppTest.from_function(index_preview_app).run(timeout=20)
    assert not app.exception
    assert not app.dataframe
    app.toggle(key="overview_show_demo_indices").set_value(True).run(timeout=20)
    assert not app.exception
    assert app.dataframe[0].value["点位"].tolist() == [1234.5]
    assert any("非真实报价" in item.value for item in app.caption)


def test_workspace_toolbar_routes_and_searches_stock():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.run(timeout=30)
    app.button(key="workspace_route_大盘云图").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["active_nav"] == "大盘云图"
    app.text_input(key="workspace_stock_query").set_value("688008")
    next(button for button in app.button if button.label == "查看个股").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["active_nav"] == "个股详情"
    assert app.session_state["stock_detail_query"] == "688008"


def test_terminal_preset_applies_color_and_minimum_defaults():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)
    app.number_input(key="terminal_minimum").set_value(8).run(timeout=30)
    app.segmented_control(key="terminal_preset").set_value("行业强弱").run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="terminal_color").value == "行业强度"
    assert app.number_input(key="terminal_minimum").value == 1
    app.segmented_control(key="terminal_preset").set_value("细分机会").run(timeout=30)
    assert not app.exception
    assert app.number_input(key="terminal_minimum").value == 3


def test_stock_detail_can_browse_next_and_previous_candidates():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)
    first = app.selectbox(key="stock_detail_selection").value
    assert app.button(key="detail_previous_stock").disabled
    app.button(key="detail_next_stock").click().run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="stock_detail_selection").value != first
    app.button(key="detail_previous_stock").click().run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="stock_detail_selection").value == first


def test_overview_rankings_switch_and_open_selected_stock():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.run(timeout=30)
    app.segmented_control(key="overview_sector_rank_mode").set_value("领跌").run(timeout=30)
    app.segmented_control(key="overview_stock_rank_mode").set_value("领跌个股").run(timeout=30)
    assert not app.exception
    selected = app.selectbox(key="summary_stock_jump").value.split(" · ", 1)[0]
    app.button(key="summary_open_stock").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["active_nav"] == "个股详情"
    assert app.session_state["stock_detail_query"] == selected


def test_stock_detail_exposes_saved_snapshot_review():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "多日个股复盘" for item in app.subheader)


def test_market_quote_origin_distinguishes_import_from_demo():
    assert market_quote_origin({"stock_quote_source": "imported", "import_date": "2026-09-28"}) == "导入行情快照｜截至交易日：2026-09-28"
    assert market_quote_origin({"stock_quote_source": "demo", "import_date": None}) == "演示行情｜非真实市场报价"


def test_capital_replay_page_offers_snapshot_upload():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "板块资金流向"
    app.run(timeout=30)

    assert not app.exception
    assert any(title.value == "板块资金流向" for title in app.title)
    assert len(app.file_uploader) == 1


def test_market_navigation_exposes_sector_capital_flow_entry():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.run(timeout=30)

    assert any("板块资金流向" in radio.options for radio in app.radio)


def test_market_terminal_shows_rotation_research_panel():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.session_state["terminal_workspace_mode"] = "深度研究"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "行业轮动观察" for item in app.subheader)


def test_market_terminal_shows_market_pulse_route():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.session_state["terminal_workspace_mode"] = "深度研究"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "云图市场脉冲" for item in app.subheader)


def test_market_terminal_shows_a_research_queue():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.session_state["terminal_workspace_mode"] = "深度研究"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "云图研究清单" for item in app.subheader)


def test_market_terminal_shows_turnover_structure_in_the_right_rail():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "成交结构" for item in app.subheader)


def test_market_terminal_without_size_data_labels_equal_area_and_unknown_turnover():
    def render():
        import pandas as pd
        from src.pages_public import render_market_terminal

        stocks = pd.DataFrame({
            "代码": ["000001", "000002", "000003"],
            "名称": ["甲", "乙", "丙"],
            "行业": ["电子", "电子", "银行"],
            "涨跌幅": [1.0, -1.0, 0.5],
        })
        render_market_terminal({"stocks": stocks, "market_history": pd.DataFrame(), "stock_quote_source": "imported", "import_date": "2026-09-29"})

    app = AppTest.from_function(render).run(timeout=30)

    assert not app.exception
    assert any("等面积" in item.value for item in app.info)
    assert any("市值不替代成交额" in item.value for item in app.caption)


def test_market_terminal_shows_after_close_trend_in_the_right_rail():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "收盘趋势" for item in app.subheader)
    assert any(set(item.options) >= {"上涨广度", "平均涨跌", "成交额"} for item in app.segmented_control)


def test_market_terminal_shows_return_distribution_in_the_right_rail():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "涨跌统计" for item in app.subheader)


def test_market_terminal_shows_a_control_console_before_the_map():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.label == "云图视角" for item in app.segmented_control)
    assert any(item.label == "云图面积" for item in app.selectbox)


def test_market_terminal_links_selected_industry_to_capital_replay():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.session_state["terminal_workspace_mode"] = "深度研究"
    app.run(timeout=30)

    assert not app.exception
    assert any(button.label == "对照行业资金流向" for button in app.button)


def test_market_terminal_defaults_to_a_single_screen_cloud_workspace():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value.startswith("全市场 · ") and item.value.endswith("地图") for item in app.subheader)
    assert any(item.label == "工作区" and item.value == "一屏云图" for item in app.segmented_control)


def test_market_terminal_keeps_the_industry_research_context_visible():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.session_state["research_context"] = {"source": "市场总览", "industry": "半导体"}
    app.run(timeout=30)

    assert not app.exception
    assert any("当前研究路径：市场总览 → 半导体" in item.value for item in app.info)


def test_sidebar_exposes_a_global_research_path_reset():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "市场总览"
    app.session_state["research_context"] = {"source": "市场总览", "industry": "半导体"}
    app.run(timeout=30)

    assert not app.exception
    assert any(button.label == "清除当前研究路径" for button in app.button)


def test_stock_detail_shows_relative_position_panel():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "相对位置坐标" for item in app.subheader)


def test_stock_detail_shows_after_close_research_snapshot():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)

    assert not app.exception
    assert any("研究归属：" in item.value for item in app.caption)


def detail_quote_fixture():
    import pandas as pd
    from src.pages_public import render_stock_detail
    stocks = pd.DataFrame({"代码": [1], "名称": ["测试公司"], "价格": [99.0],
                           "涨跌幅": [1.0], "板块": ["电子"], "成交额": [1e8],
                           "昨收价": [10.0], "开盘价": [11.0], "最高价": [12.0]})
    render_stock_detail({"stocks": stocks, "stock_quote_source": "imported", "import_date": "2026-09-16"})


def test_stock_detail_quote_facts_normalize_code_and_preserve_missing_low():
    app = AppTest.from_function(detail_quote_fixture).run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="stock_detail_selection").value == "000001 · 测试公司"
    quote_table = next(item.value for item in app.table if "昨收" in item.value.index)
    assert quote_table.loc["昨收"].iloc[0] == "10.00"
    assert quote_table.loc["今开"].iloc[0] == "11.00"
    assert quote_table.loc["最低"].iloc[0] == "—"


def test_peer_ranking_sorts_numeric_quotes_and_keeps_missing_turnover_unknown():
    import pandas as pd
    from src.pages_public import rank_peer_quotes
    peers = pd.DataFrame({"代码": ["1", "2", "3"], "涨跌幅": ["2", "10", None],
                          "成交额": [None, "100", "20"]})
    ranked = rank_peer_quotes(peers, "涨跌幅")
    assert ranked["代码"].tolist() == ["2", "1", "3"]
    assert pd.isna(ranked.loc[ranked["代码"].eq("1"), "成交额"].iloc[0])
    assert rank_peer_quotes(peers, "成交额", ascending=True)["代码"].tolist() == ["3", "2", "1"]


def peer_sort_fixture():
    import pandas as pd
    from src.pages_public import render_stock_detail
    stocks = pd.DataFrame({"代码": ["000001", "000002", "000003", "000004"],
                           "名称": ["当前", "领涨", "活跃", "未知"], "板块": ["电子"] * 4,
                           "价格": [10] * 4, "涨跌幅": [1, 10, 2, None],
                           "成交额": [10e8, 1e8, 3e8, None]})
    render_stock_detail({"stocks": stocks, "stock_quote_source": "imported", "import_date": "2026-09-16"})


def test_peer_board_sort_changes_visible_order_without_filling_missing_turnover():
    app = AppTest.from_function(peer_sort_fixture).run(timeout=30)
    assert not app.exception
    app.selectbox(key="detail_peer_sort").select("成交额").run(timeout=30)
    assert not app.exception
    tables = [item.value for item in app.dataframe if "代码" in item.value and len(item.value) == 3]
    assert tables[-1]["代码"].tolist() == ["000003", "000002", "000004"]
    assert tables[-1]["成交额"].isna().sum() == 1
    app.segmented_control(key="detail_peer_direction").set_value("从低到高").run(timeout=30)
    tables = [item.value for item in app.dataframe if "代码" in item.value and len(item.value) == 3]
    assert tables[-1]["代码"].tolist() == ["000002", "000003", "000004"]
    assert not app.exception


def test_stock_detail_shows_after_close_review_points():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "盘后复盘要点" for item in app.subheader)


def test_index_analysis_shows_close_review_pulse():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "指数分析"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "指数市场脉冲" for item in app.subheader)


def test_concept_ranking_shows_strength_tier_review():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "概念排行"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "板块强弱梯队" for item in app.subheader)


def test_capital_replay_shows_data_readiness_panel():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "板块资金流向"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "回放数据完整度" for item in app.subheader)


def test_capital_replay_exposes_research_linkage_section():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "板块资金流向"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "资金研究联动" for item in app.subheader)


def test_industry_chain_shows_research_overview():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "产业链分层"
    app.run(timeout=30)
    assert app.segmented_control(key="chain_panorama_view").value == "PCB 参考全景"
    assert len(app.dataframe) == 4
    app.segmented_control(key="chain_panorama_view").set_value("综合链条").run(timeout=30)

    assert not app.exception
    assert any(item.value == "产业链研究总览" for item in app.subheader)


def test_sector_heatmap_shows_cloud_research_path():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "板块热力图"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "云图研究路径" for item in app.subheader)


def test_candidate_scanner_shows_close_research_path():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "盘中选股"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "收盘候选研究路径" for item in app.subheader)


def test_candidate_cards_update_preview_and_open_the_same_stock():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "盘中选股"
    app.run(timeout=30)
    app.button(key="scanner_candidate_1").click().run(timeout=30)
    assert not app.exception
    selected = app.selectbox(key="scanner_stock_jump").value.split(" · ", 1)[0]
    assert any(selected in heading.value for heading in app.subheader)
    app.button(key="scanner_open_detail").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["stock_detail_query"] == selected


def test_candidate_reset_recovers_from_empty_literal_search():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "盘中选股"
    app.run(timeout=30)
    app.text_input(key="scanner_query").set_value("[no-match]").run(timeout=30)
    assert not app.exception
    assert any("没有匹配的候选" in item.value for item in app.info)
    app.button(key="scanner_reset_filters").click().run(timeout=30)
    assert not app.exception
    assert app.text_input(key="scanner_query").value == ""
    assert app.selectbox(key="scanner_stock_jump").value


def test_candidate_selection_survives_detail_round_trip():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "盘中选股"
    app.run(timeout=30)
    app.slider(key="scanner_min_change").set_value(-5.0).run(timeout=30)
    app.button(key="scanner_candidate_1").click().run(timeout=30)
    selected = app.selectbox(key="scanner_stock_jump").value
    app.button(key="scanner_open_detail").click().run(timeout=30)
    app.button(key="workspace_route_盘中选股").click().run(timeout=30)
    assert not app.exception
    assert app.slider(key="scanner_min_change").value == -5.0
    assert app.selectbox(key="scanner_stock_jump").value == selected


def test_cloud_quick_focus_and_reset_restore_all_market():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)
    group = app.selectbox(key="terminal_quick_group").options[1]
    app.selectbox(key="terminal_quick_group").select(group).run(timeout=30)
    app.button(key="terminal_quick_focus").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["terminal_industry_query"] == group
    app.button(key="terminal_quick_reset").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["terminal_industry_query"] == ""


def test_market_overview_shows_close_review_summary():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "市场总览"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "收盘市场脉冲" for item in app.subheader)


def test_market_overview_shows_next_day_research_route():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "市场总览"
    app.run(timeout=30)

    assert not app.exception
    assert any(item.value == "次日研究路径" for item in app.subheader)


def test_market_overview_marks_the_snapshot_as_of_date():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "市场总览"
    app.run(timeout=30)

    assert not app.exception
    assert any("截至交易日" in item.value for item in app.caption)


def test_market_overview_shows_market_radar():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.session_state["active_nav"] = "市场总览"
    app.run(timeout=30)

    assert not app.exception
    assert any("领涨" in item.value and "规模活跃" in item.value for item in app.caption)


def test_sidebar_shows_unconfigured_feishu_status_without_crashing(monkeypatch):
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.run(timeout=30)

    assert not app.exception
    assert any("飞书通知：未配置" in item.value for item in app.caption)
    assert any(button.label == "发送飞书测试通知" for button in app.button)


def test_unconfigured_feishu_test_button_shows_setup_hint_without_crashing(monkeypatch):
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.run(timeout=30)
    next(button for button in app.button if button.label == "发送飞书测试通知").click()
    app.run(timeout=30)

    assert not app.exception
    assert any("FEISHU_WEBHOOK_URL" in item.value for item in app.info)
