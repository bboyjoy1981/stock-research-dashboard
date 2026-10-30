from streamlit.testing.v1 import AppTest


def test_overview_map_prefers_capitalization_and_can_switch_to_turnover():
    app = AppTest.from_string('''
import pandas as pd
from src.core_workspace import render_overview_map
stocks = pd.DataFrame({'代码':['600001','600002'], '名称':['甲','乙'],
 '行业':['银行','电子'], '涨跌幅':[1,-1], '总市值':[1000,500], '成交额':[10,30]})
render_overview_map(stocks,'行业','成交额')
''').run()
    assert not app.exception
    assert app.selectbox(key='overview_map_area').value == '总市值'
    assert any('面积=总市值' in item.value for item in app.caption)
    app.selectbox(key='overview_map_area').select('成交额').run()
    assert not app.exception
    assert any('面积=成交额' in item.value for item in app.caption)
    app.button(key='overview_full_cloud').click().run()
    assert not app.exception
    assert app.session_state['terminal_size'] == '成交额'
    assert app.session_state['terminal_level'] == '行业'
    assert app.session_state['active_nav'] == '大盘云图'


def test_overview_map_falls_back_when_capitalization_is_missing():
    app = AppTest.from_string('''
import pandas as pd
from src.core_workspace import render_overview_map
stocks = pd.DataFrame({'代码':['600001'], '名称':['甲'], '行业':['银行'],
 '涨跌幅':[1], '总市值':[None], '成交额':[10]})
render_overview_map(stocks,'行业','成交额')
''').run()
    assert not app.exception
    assert app.selectbox(key='overview_map_area').options == ['成交额']
    assert app.selectbox(key='overview_map_area').value == '成交额'
