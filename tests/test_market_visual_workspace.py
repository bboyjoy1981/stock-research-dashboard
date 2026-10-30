import json
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_overview_opens_with_real_market_tiles_and_can_switch_to_ranking():
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert app.segmented_control(key='overview_visual_mode').value == '市场云图'
    charts = [json.loads(item.proto.spec) for item in app.get('plotly_chart')]
    assert any(chart['data'][0]['type'] == 'treemap' for chart in charts)
    app.segmented_control(key='overview_visual_mode').set_value('行业排行').run(timeout=30)
    assert not app.exception
    assert not any(json.loads(item.proto.spec)['data'][0]['type'] == 'treemap' for item in app.get('plotly_chart'))
    assert app.selectbox(key='overview_primary_industry').options


def test_overview_cloud_jump_opens_full_market_not_previous_sector():
    app = AppTest.from_file(APP)
    app.session_state['terminal_industry_query'] = '银行'
    app.session_state['core_cloud_group'] = '银行'
    app.run(timeout=30)
    app.button(key='overview_full_cloud').click().run(timeout=30)
    assert not app.exception
    assert app.session_state['active_nav'] == '大盘云图'
    assert app.session_state['terminal_industry_query'] == ''
    assert app.selectbox(key='core_cloud_group').value == '全部'


def test_workspace_search_is_available_in_compact_toolbar():
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert app.text_input(key='workspace_stock_query').placeholder == '股票代码或名称'
    assert not any(any(widget.key == 'workspace_stock_query' for widget in item.text_input)
                   for item in app.get('popover'))
    app.text_input(key='workspace_stock_query').set_value('688008').run(timeout=30)
    assert not app.exception
    assert app.session_state['active_nav'] == '个股详情'
    assert app.session_state['stock_detail_query'] == '688008'


def test_overview_zero_turnover_uses_positive_market_cap_tiles():
    app = AppTest.from_string('''
import pandas as pd
from src.pages_public import render_market_overview
stocks = pd.DataFrame({'代码': ['600000', '600001'], '名称': ['甲', '乙'],
                       '行业': ['电子', '银行'], '涨跌幅': [1, -1],
                       '成交额': [0, 0], '流通市值': [200, 100]})
render_market_overview({'stocks': stocks, 'stock_quote_source': 'imported',
                       'import_date': '2026-09-16'})
''').run(timeout=30)
    assert not app.exception
    trees = [json.loads(item.proto.spec) for item in app.get('plotly_chart')
             if json.loads(item.proto.spec)['data'][0]['type'] == 'treemap']
    assert len(trees) == 1
    assert any('面积=流通市值' in item.value for item in app.caption)
