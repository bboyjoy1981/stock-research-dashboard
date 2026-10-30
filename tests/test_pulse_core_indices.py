from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_core_indices_are_in_pulse_without_demo_quotes():
    app = AppTest.from_string('''
from src.demo_data import load_demo_market
from src.pages_public import render_market_overview
render_market_overview(load_demo_market())
''').run(timeout=30)
    assert not app.exception
    assert '核心指数 · 收盘行情' in [item.value for item in app.subheader]
    assert any('未导入真实指数行情' in item.value for item in app.info)
    assert '北证50' not in [item.label for item in app.metric]


def test_core_indices_display_real_snapshot_instead_of_demo():
    app = AppTest.from_string('''
import pandas as pd
from src.demo_data import load_demo_market
from src.pages_public import render_market_overview
data = load_demo_market()
data['index_snapshot'] = pd.DataFrame([{
    '名称': '上证指数', '价格': 3842.19, '涨跌幅': .31,
    '涨跌': 11.74, '源时间': '20260930161500', '来源': '测试真实快照'
}])
render_market_overview(data)
''').run(timeout=30)
    assert not app.exception
    metric = next(item for item in app.metric if item.label == '上证指数')
    assert metric.value == '3,842.19'
    assert metric.delta == '+0.31%'
    missing = next(item for item in app.metric if item.label == '沪深300')
    assert missing.value == '待接入'
