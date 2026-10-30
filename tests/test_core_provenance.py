import pandas as pd
from streamlit.testing.v1 import AppTest


def test_exported_snapshot_date_is_recognized_on_reimport():
    from src.importers import infer_import_date
    assert infer_import_date(pd.DataFrame({'快照日期': ['2026-09-16']})) == '2026-09-16'


def test_export_carries_demo_source_and_cannot_be_imported_as_real_quotes():
    from src.core_workspace import quote_export
    from src.importers import validate_stock_pool
    frame = pd.DataFrame({'代码': ['600000'], '名称': ['甲'], '板块': ['银行'], '涨跌幅': [1]})
    exported = quote_export(frame, {'stock_quote_source': 'demo'})
    assert exported['行情来源'].tolist() == ['演示数据']
    assert any('演示' in error for error in validate_stock_pool(exported))


def test_cloud_export_preserves_source():
    from src.cloud_scope import cloud_scope_export
    result = cloud_scope_export(pd.DataFrame({'个股': ['600000 · 甲']}), date=None, area='等权', color='平均涨跌幅', source='demo')
    assert result['行情来源'].tolist() == ['演示数据']


def test_deep_cloud_components_keep_selected_parent():
    app = AppTest.from_string('''
import pandas as pd
from src.pages_public import render_market_terminal
frame = pd.DataFrame({'代码':['600000','600001','600002'], '名称':['甲','乙','丙'],
 '行业':['电子','通信','电子'], '细分行业':['半导体','半导体','半导体设备'],
 '板块':['主板']*3, '涨跌幅':[1,-2,3], '成交额':[100,200,300]})
render_market_terminal({'stocks':frame})
''')
    app.session_state['terminal_level'] = '细分行业'
    app.session_state['terminal_workspace_mode'] = '深度研究'
    app.session_state['core_cloud_parent'] = '电子'
    app.session_state['core_cloud_group'] = '半导体'
    app.run(timeout=30)
    assert not app.exception
    assert app.selectbox(key='terminal_stock_jump').options == ['600000 · 甲']
