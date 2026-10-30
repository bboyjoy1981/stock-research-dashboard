from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_overview_separates_market_industry_and_quotes_into_peer_workspaces():
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    tabs = {tab.label: tab for tab in app.tabs}
    assert {'市场地图', '行业研究', '行情榜单'}.issubset(tabs)
    assert tabs['市场地图'].get('plotly_chart')
    assert any(item.value == '行业研究台' for item in tabs['行业研究'].subheader)
    assert tabs['行情榜单'].selectbox(key='overview_stock_scope').options
    assert app.session_state['overview_workspace'] == '市场地图'


def test_industry_members_action_reveals_filtered_quote_workspace():
    app = AppTest.from_file(APP).run(timeout=30)
    target = app.selectbox(key='overview_primary_industry').options[0]
    app.selectbox(key='overview_primary_industry').set_value(target).run(timeout=30)
    app.button(key='overview_primary_members').click().run(timeout=30)
    assert not app.exception
    assert app.session_state['overview_workspace'] == '行情榜单'
    assert app.selectbox(key='overview_stock_scope').value == target
