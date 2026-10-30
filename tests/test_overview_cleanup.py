from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_overview_removes_duplicate_panels_and_keeps_review_tools():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    assert not app.exception
    panels = [item.label for item in [*app.expander, *app.status]]
    assert '市场研究驾驶台 · 详细指标与入口' not in panels
    assert '指数数据与演示布局' not in panels
    assert '市场深度研究 · 重点方向与轮动' not in panels
    assert '收盘快照变化对照' in panels
    assert '多日市场回放' in panels
    assert '导出当前市场快照' in panels
    assert not any('附近' in item.label for item in app.metric)
    industry_tab = next(tab for tab in app.tabs if tab.label == '行业研究')
    assert any('优先研究' in item.value for item in industry_tab.subheader)


def test_overview_review_and_exports_live_in_report_not_global_footer():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    assert not app.exception
    tabs = {tab.label: tab for tab in app.tabs}
    report_panels = {panel.label for panel in [*tabs['收盘报告'].expander, *tabs['收盘报告'].status]}
    assert {'收盘快照变化对照', '多日市场回放', '导出当前市场快照'} <= report_panels
    assert '次日研究路径 · 方向与代表个股' in {p.label for p in [*tabs['行业研究'].expander, *tabs['行业研究'].status]}
    assert not tabs['市场地图'].get('download_button')
    assert not any('市场状态' in item.value for item in tabs['收盘报告'].text)
