import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize('industry', [None, '全部', '未分类', '未细分', float('nan'), ''])
def test_open_unknown_industry_does_not_keep_previous_sector(industry):
    app = AppTest.from_string('''
import streamlit as st
from src.core_workspace import open_core_stock
st.button('打开', on_click=open_core_stock, args=('600000 · 甲', st.session_state['industry']))
''')
    app.session_state['industry'] = industry
    app.session_state['research_context'] = {'source': '旧云图', 'industry': '半导体'}
    app.run().button[0].click().run()
    assert not app.exception
    assert 'research_context' not in app.session_state
    assert app.session_state['stock_detail_query'] == '600000'


def test_unknown_source_is_not_presented_as_demo():
    from src.core_workspace import snapshot_status
    result = snapshot_status({'stocks': pd.DataFrame(), 'stock_quote_source': 'unavailable'})
    assert result['source'] == '来源未识别'
