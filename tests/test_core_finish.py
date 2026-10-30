from pathlib import Path
import datetime as dt
import pandas as pd
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_snapshot_status_separates_missing_quotes_from_flat():
    from src.core_workspace import snapshot_status
    data = {'stocks': pd.DataFrame({'涨跌幅': [1, 0, None, -2]}),
            'stock_quote_source': 'imported', 'import_date': '2026-09-16'}
    result = snapshot_status(data, today=dt.date(2026, 10, 4))
    assert result == {'rows': 4, 'valid': 3, 'unknown': 1, 'coverage': .75,
                      'date': '2026-09-16', 'age': 18, 'source': '导入快照'}


def test_exact_drill_keeps_parent_and_does_not_match_substrings():
    from src.core_workspace import filter_map_scope
    frame = pd.DataFrame({'行业': ['电子', '电子', '通信'],
                          '细分行业': ['半导体', '半导体设备', '半导体'], '代码': ['1', '2', '3']})
    selected = filter_map_scope(frame, {'行业': '电子', '细分行业': '半导体'})
    assert selected['代码'].tolist() == ['1']
    assert len(frame) == 3


def test_overview_primary_sector_focus_filters_stock_ranking():
    app = AppTest.from_file(APP).run(timeout=30)
    target = app.selectbox(key='overview_primary_industry').options[0]
    app.selectbox(key='overview_primary_industry').select(target).run(timeout=30)
    app.button(key='overview_primary_members').click().run(timeout=30)
    assert not app.exception
    assert app.selectbox(key='overview_stock_scope').value == target
    app.button(key='overview_primary_cloud').click().run(timeout=30)
    assert not app.exception
    assert app.session_state['active_nav'] == '大盘云图'
    assert app.session_state['terminal_industry_query'] == target


def test_cloud_one_screen_has_immediate_components_and_full_reset():
    app = AppTest.from_file(APP)
    app.session_state['active_nav'] = '大盘云图'
    app.run(timeout=30)
    app.selectbox(key='core_cloud_group').select('半导体').run(timeout=30)
    assert not app.exception
    assert app.selectbox(key='core_cloud_stock').options
    app.button(key='core_cloud_open_stock').click().run(timeout=30)
    assert not app.exception
    assert app.session_state['active_nav'] == '个股详情'
    assert app.session_state['stock_detail_query']


def test_sidebar_clear_also_resets_exact_drill():
    app = AppTest.from_file(APP)
    app.session_state['research_context'] = {'source': '云图', 'industry': '半导体'}
    app.session_state['core_cloud_group'] = '半导体'
    app.session_state['core_cloud_parent'] = '电子'
    app.session_state['terminal_quick_group'] = '半导体'
    app.run(timeout=30)
    app.button(key='sidebar_clear_research_path').click().run(timeout=30)
    assert not app.exception
    assert app.session_state['core_cloud_group'] == '全部'
    assert app.session_state['core_cloud_parent'] == '全部'
    assert app.session_state['terminal_quick_group'] == '全市场'


def test_unknown_only_overview_does_not_classify_as_normal_market():
    app = AppTest.from_string('''
import pandas as pd
from src.pages_public import render_market_overview
render_market_overview({'stocks': pd.DataFrame({'代码': ['600000'], '名称': ['未知'], '涨跌幅': [None]})})
''').run(timeout=30)
    assert not app.exception
    assert app.warning
    assert not app.metric


def test_map_missing_area_is_not_fabricated_as_equal_weight():
    from src.calculations import market_map_leaves
    frame = pd.DataFrame({'代码': ['600000', '600001'], '名称': ['甲', '乙'],
                          '行业': ['银行', '银行'], '涨跌幅': [1, -1], '成交额': [None, 0]})
    leaves = market_map_leaves(frame, pd.DataFrame(), '行业', '成交额', '涨跌幅')
    assert leaves.empty


def test_detail_clear_returns_to_all_market_without_old_selection():
    app = AppTest.from_file(APP)
    app.session_state['active_nav'] = '个股详情'
    app.session_state['stock_detail_query'] = '688008'
    app.session_state['research_context'] = {'source': '云图', 'industry': '半导体'}
    app.run(timeout=30)
    app.button(key='detail_clear_search').click().run(timeout=30)
    assert not app.exception
    assert app.text_input(key='stock_detail_query').value == ''
    assert len(app.selectbox(key='stock_detail_selection').options) > 1
    assert 'research_context' not in app.session_state


def test_parent_switch_discards_invalid_child_without_losing_parent_scope():
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from src.core_workspace import render_exact_cloud_scope
frame = pd.DataFrame({'行业': ['电子', '通信'], '细分行业': ['半导体', '设备']})
result = render_exact_cloud_scope(frame, '细分行业', '行业')
st.dataframe(result)
''').run()
    app.selectbox(key='core_cloud_parent').select('电子').run()
    app.selectbox(key='core_cloud_group').select('半导体').run()
    app.selectbox(key='core_cloud_parent').select('通信').run()
    assert not app.exception
    assert app.selectbox(key='core_cloud_group').value == '全部'
    assert app.dataframe[0].value['行业'].tolist() == ['通信']


def test_legacy_map_focus_can_update_query_after_inputs_render():
    app = AppTest.from_file(APP)
    app.session_state['active_nav'] = '大盘云图'
    app.run(timeout=30)
    options = app.selectbox(key='terminal_map_industry').options
    target = '半导体' if '半导体' in options else options[0]
    app.selectbox(key='terminal_map_industry').select(target).run(timeout=30)
    app.button(key='terminal_map_focus').click().run(timeout=30)
    assert not app.exception
    assert app.text_input(key='terminal_industry_query').value == target


def test_exact_cloud_reset_restores_full_map_scope():
    app = AppTest.from_file(APP)
    app.session_state['active_nav'] = '大盘云图'
    app.run(timeout=30)
    app.selectbox(key='core_cloud_group').select('半导体').run(timeout=30)
    stock_count = len(app.selectbox(key='core_cloud_stock').options)
    app.button(key='terminal_quick_reset').click().run(timeout=30)
    assert not app.exception
    assert app.selectbox(key='core_cloud_group').value == '全部'
    assert len(app.selectbox(key='core_cloud_stock').options) > stock_count
