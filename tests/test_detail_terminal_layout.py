from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_detail_separates_peer_profile_history_and_data_workspaces():
    app = AppTest.from_file(APP)
    app.session_state['active_nav'] = '个股详情'
    app.session_state['stock_detail_query'] = '688008'
    app.run(timeout=30)
    assert not app.exception
    tabs = {tab.label: tab for tab in app.tabs}
    assert {'同业比较', '行情画像', '历史复盘', '数据核对'}.issubset(tabs)
    assert tabs['同业比较'].selectbox(key='detail_peer_sort').options
    assert any(item.value == '研究画像' for item in tabs['行情画像'].subheader)
    assert any(item.value == '多日个股复盘' for item in tabs['历史复盘'].subheader)
    audit = next(item.value for item in tabs['数据核对'].dataframe if '快照值' in item.value)
    assert audit.shape[0] > 4
    assert app.session_state['detail_workspace'] == '行情画像'


def test_detail_data_audit_keeps_missing_fields_visible():
    app = AppTest.from_file(APP)
    app.session_state['active_nav'] = '个股详情'
    app.session_state['stock_detail_query'] = '688008'
    app.run(timeout=30)
    audit = next(item.value for item in app.dataframe if '快照值' in item.value)
    assert {'字段', '快照值', '状态'}.issubset(audit.columns)
    assert '代码' in audit['字段'].tolist()
    assert '688008' in audit['快照值'].tolist()
