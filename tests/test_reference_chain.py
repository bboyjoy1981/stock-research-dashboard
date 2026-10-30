import pandas as pd


def test_reference_summary_uses_only_valid_changes_and_reports_unknowns():
    from src.reference_chain import reference_summary
    result = reference_summary(pd.DataFrame({"行情状态": ["已匹配快照", "已匹配快照", "快照未覆盖"],
                                              "涨跌幅": [2.0, None, None]}))
    assert result == {"rows": 3, "matched": 2, "valid": 1, "unknown": 2, "average": 2.0}
    assert reference_summary(pd.DataFrame({"行情状态": [], "涨跌幅": []}))["average"] is None


def test_layer_switch_keeps_only_selected_layer_cards_and_quotes():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(reference_app).run(timeout=20)
    app.selectbox(key="pcb_reference_layer").select("PCB 制造").run(timeout=20)
    assert not app.exception
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value["代码"].tolist() == ["603228", "002916", "002938", "001389", "002384", "002463", "688183", "300476", "002436"]
    assert len([b for b in app.button if b.key and b.key.startswith("pcb_member_")]) == 9


def test_reset_restores_all_layers_after_search():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(reference_app).run(timeout=20)
    app.text_input(key="pcb_reference_query").set_value("金安").run(timeout=20)
    app.button(key="pcb_reference_reset").click().run(timeout=20)
    assert not app.exception
    assert app.text_input(key="pcb_reference_query").value == ""
    assert len(app.dataframe) == 4


def test_reference_export_preserves_unknowns_and_filter_provenance():
    from src.reference_chain import reference_export
    quotes = pd.DataFrame({"代码": ["002636"], "价格": [None]})
    exported = reference_export(quotes, "2026-09-16", "金安", "全部分层", "涨幅降序", True)
    assert exported["代码"].tolist() == ["002636"]
    assert pd.isna(exported.iloc[0]["价格"])
    assert exported.iloc[0]["快照日期"] == "2026-09-16"
    assert exported.iloc[0]["筛选关键词"] == "金安"
    assert exported.iloc[0]["仅快照覆盖"] == True
    assert "快照日期" not in quotes


def test_reference_filter_is_literal_and_excludes_only_unmatched_when_requested():
    from src.reference_chain import filter_reference_quotes
    quotes = pd.DataFrame({"代码": ["002636", "688519", "603186"], "名称": ["甲", "乙", "丙"],
                           "分层": ["上游"] * 3, "行情状态": ["已匹配快照", "快照未覆盖", "已匹配快照"],
                           "涨跌幅": [2, None, 5]})
    assert filter_reference_quotes(quotes, matched_only=True, sort="涨幅降序")["代码"].tolist() == ["603186", "002636"]
    assert filter_reference_quotes(quotes, query="[").empty
    assert filter_reference_quotes(quotes, query="乙")["代码"].tolist() == ["688519"]


def test_reference_keyword_keeps_only_matching_card_and_quote_table():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(reference_app).run(timeout=20)
    app.text_input(key="pcb_reference_query").set_value("金安").run(timeout=20)
    assert not app.exception
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value["代码"].tolist() == ["002636"]
    assert len([b for b in app.button if b.key and b.key.startswith("pcb_member_")]) == 1


def test_reference_members_match_codes_without_inventing_missing_quotes():
    from src.reference_chain import reference_quotes
    quotes = reference_quotes(pd.DataFrame({"代码": [2636], "名称": ["金安国纪"], "价格": [12.3], "涨跌幅": [None]}))
    first = quotes.loc[quotes["代码"].eq("002636")].iloc[0]
    assert first["价格"] == 12.3
    assert pd.isna(first["涨跌幅"])
    missing = quotes.loc[quotes["代码"].eq("688519")].iloc[0]
    assert pd.isna(missing["价格"])
    assert missing["行情状态"] == "快照未覆盖"


def reference_app():
    import pandas as pd
    from src.reference_chain import render_reference_chain
    render_reference_chain({"stocks": pd.DataFrame({"代码": ["002636"], "价格": [12.3]}), "import_date": "2026-09-16"})


def test_reference_panorama_has_four_quote_groups_and_stock_route():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(reference_app).run(timeout=20)
    assert not app.exception
    assert len(app.dataframe) == 4
    assert app.dataframe[0].value.iloc[0]["代码"] == "002636"
    assert app.button(key="pcb_member_002636").label == "金安国纪"
    app.button(key="pcb_member_002636").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["active_nav"] == "个股详情"
    assert app.session_state["stock_detail_query"] == "002636"
