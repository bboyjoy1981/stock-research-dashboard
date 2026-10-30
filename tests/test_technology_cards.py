import pandas as pd
from streamlit.testing.v1 import AppTest


def test_technology_filter_uses_reference_layers_without_classifying_all_electronics():
    from src.technology_cards import classify_technology
    source = pd.DataFrame({'代码': ['002916', '600183', '300308', '000001'],
                           '细分行业': ['印制电路板', '电子材料', '通信网络设备', '银行'],
                           '标签': ['', '', 'CPO', '']})
    result = classify_technology(source)
    assert result['科技方向'].tolist() == ['PCB', 'PCB', '光通信 / CPO', '其他 / 未分类']
    assert result.loc[0, '科技细分'] == 'PCB 制造'
    assert result.loc[1, '科技细分'] == '上游原材料 / 覆铜板 CCL'
    assert '参考名单' in result.loc[0, '分类依据']
    assert '科技方向' not in source


def test_price_range_never_invents_missing_or_inconsistent_ohlc():
    from src.technology_cards import price_range
    assert price_range({'价格': 12, '最低价': 10, '最高价': 14}) == (10, 14, .5)
    assert price_range({'价格': 12}) is None
    assert price_range({'价格': 12, '最低': 14, '最高': 10}) is None
    assert price_range({'价格': 16, '最低': 10, '最高': 14}) is None


def test_empty_theme_remains_selectable_and_market_limits_industry_options():
    app = AppTest.from_function(render_technology_fixture).run(timeout=20)
    assert '商业航天与卫星' in app.selectbox(key='scanner_technology').options
    assert '光通信 / CPO' in app.selectbox(key='scanner_technology').options
    app.selectbox(key='scanner_technology').select('商业航天与卫星').run()
    assert not app.exception
    assert not [b for b in app.button if str(b.key).startswith('scanner_candidate_')]
    app.selectbox(key='scanner_technology').select('全部').run()
    app.selectbox(key='scanner_market').select('科创板').run()
    assert app.selectbox(key='scanner_group').options == ['全部']


def render_technology_fixture():
    from src.pages_scanner import render_candidate_workspace
    import pandas as pd
    render_candidate_workspace({'stocks': pd.DataFrame({
        '代码': ['002916', '600183', '000001'], '名称': ['深南电路', '生益科技', '银行'],
        '细分行业': ['印制电路板', '电子材料', '银行'],
        '价格': [12, 20, 10], '涨跌幅': [2, 1, 3], '成交额': [2e8, 3e8, 1e8],
        '总市值': [10e8, 20e8, 30e8], '最低': [10, 18, 9], '最高': [14, 22, 11],
    }), 'import_date': '2026-09-30', 'stock_quote_source': 'imported'})


def test_technology_and_layer_filters_link_cards_preview_and_export():
    app = AppTest.from_function(render_technology_fixture).run(timeout=20)
    assert not app.exception
    app.selectbox(key='scanner_technology').select('PCB').run()
    app.selectbox(key='scanner_technology_layer').select('PCB 制造').run()
    assert not app.exception
    assert app.selectbox(key='scanner_stock_jump').options == ['002916 · 深南电路']
    assert len([b for b in app.button if str(b.key).startswith('scanner_candidate_')]) == 1
    assert any('10.00 亿' in str(t.value) for t in app.table)
    app.button(key='scanner_candidate_0').click().run()
    assert app.session_state['scanner_stock_jump'] == '002916 · 深南电路'
    assert any(b.key == 'scanner_export_full' for b in app.get('download_button'))
