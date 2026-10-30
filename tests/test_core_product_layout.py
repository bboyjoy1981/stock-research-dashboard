from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_overview_rankings_and_optional_research_have_separate_tabs():
    app = AppTest.from_file(APP).run(timeout=30)
    ranking = next(tab for tab in app.tabs if tab.label == '行情榜单')
    research = next(tab for tab in app.tabs if tab.label == '行业研究')
    assert any(item.value == '活跃个股' for item in ranking.subheader)
    assert any(item.value == '优先研究细分行业' for item in research.subheader)
    assert not any(item.value == '优先研究细分行业' for item in ranking.subheader)


def test_cloud_default_does_not_silently_hide_unclassified_stocks():
    app = AppTest.from_file(APP)
    app.session_state["active_nav"] = "大盘云图"
    app.run(timeout=30)
    assert not app.exception
    assert app.toggle(key="terminal_include_unclassified").value is True


def test_detail_quote_and_peer_panels_precede_optional_profile():
    app = AppTest.from_file(APP)
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)
    assert not app.exception
    headings = [item.value for item in app.subheader]
    assert headings.index("同类对比") < headings.index("研究画像")
    # This installed Streamlit represents icon-bearing expanders as status blocks.
    panels = [*app.expander, *app.status]
    assert any(item.label == "个股深度研究 · 画像与指标" and not item.proto.expanded for item in panels)


def test_detail_uses_its_own_search_and_shows_turnover_not_missing_score():
    app = AppTest.from_file(APP)
    app.session_state["active_nav"] = "个股详情"
    app.run(timeout=30)
    assert not app.exception
    assert not any(item.key == "workspace_stock_query" for item in app.text_input)
    assert any(item.key == "stock_detail_query" for item in app.text_input)
    assert any(item.label == "换手率" for item in app.metric)
