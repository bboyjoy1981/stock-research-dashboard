import pandas as pd
from streamlit.testing.v1 import AppTest


def test_industries_preserve_missing_and_decliners():
    from src.sector_directory import prepare_stocks, industry_members
    raw = pd.DataFrame({'代码': ['000001', '000002', '000003'], '名称': ['甲', '乙', '丙'], '行业': ['银行', '银行', None], '涨跌幅': [-2, 1, None]})
    frame = prepare_stocks(raw)
    assert len(industry_members(frame, '银行')) == 2
    assert len(industry_members(frame, '未分类')) == 1
    assert raw['行业'].isna().sum() == 1


def test_themes_can_overlap_without_promoting_optics_to_cpo():
    from src.sector_directory import prepare_stocks, theme_members
    frame = prepare_stocks(pd.DataFrame({'代码': ['300001', '300002'], '名称': ['甲', '乙'], '行业': ['光模块', '软件'], '标签': ['CPO,液冷', '']}))
    assert theme_members(frame, 'CPO / 光通信')['代码'].tolist() == ['300001']
    assert theme_members(frame, '算力基础设施')['代码'].tolist() == ['300001']
    assert theme_members(frame, 'CPO / 光通信', 'CPO')['代码'].tolist() == ['300001']
    plain = prepare_stocks(pd.DataFrame({'代码': ['300003'], '名称': ['丙'], '行业': ['光模块']}))
    assert theme_members(plain, 'CPO / 光通信', 'CPO').empty


def test_pcb_reference_is_retained():
    from src.sector_directory import prepare_stocks, theme_members
    frame = prepare_stocks(pd.DataFrame({'代码': ['002916'], '名称': ['深南电路'], '行业': ['电子']}))
    members = theme_members(frame, 'PCB', 'PCB 制造')
    assert members['代码'].tolist() == ['002916']
    assert '参考名单' in members.iloc[0]['分类依据']


def test_directory_cards_and_stock_navigation():
    def script():
        import pandas as pd
        from src.sector_directory import render_sector_directory
        render_sector_directory({'stocks': pd.DataFrame({'代码': ['000001'], '名称': ['平安银行'], '行业': ['银行'], '价格': [10], '涨跌幅': [-1]}), 'import_date': '2026-10-09'})
    at = AppTest.from_function(script).run(timeout=15)
    assert not at.exception
    assert not at.dataframe
    at.button(key='sector_stock_000001').click().run()
    assert not at.exception
    assert at.session_state['active_nav'] == '个股详情'
    assert at.session_state['stock_detail_query'] == '000001'


def test_sidebar_exposes_directory_without_expander():
    def script():
        from src.ui import render_sidebar
        render_sidebar([])
    at = AppTest.from_function(script).run(timeout=15)
    assert '板块细分' in at.radio(key='market_nav').options


def test_public_route_and_empty_theme_are_safe():
    def script():
        import pandas as pd
        from src.pages_public import render_public_page
        render_public_page('板块细分', {'stocks': pd.DataFrame({'代码': ['000001'], '名称': ['平安银行'], '行业': ['银行']}), 'stock_quote_source': 'imported'})
    at = AppTest.from_function(script).run(timeout=15)
    assert not at.exception
    at.session_state['sector_mode'] = '科技精细分类'
    at.run()
    assert not at.exception
    assert at.info
    assert not any(b.key.startswith('sector_stock_') for b in at.button)


def test_listing_board_is_not_an_industry():
    from src.sector_directory import prepare_stocks
    frame = prepare_stocks(pd.DataFrame({'代码': ['000001'], '名称': ['甲'], '板块': ['创业板']}))
    assert frame.iloc[0]['浏览行业'] == '未分类'


def test_missing_subindustry_renders_and_search_resets_on_group_change():
    def script():
        import pandas as pd
        from src.sector_directory import render_sector_directory
        render_sector_directory({'stocks': pd.DataFrame({'代码': ['000001'], '名称': ['甲'], '行业': ['银行'], '细分行业': [pd.NA]})})
    at = AppTest.from_function(script).run(timeout=15)
    assert not at.exception
    at.session_state['sector_layer'] = '未细分'
    at.run()
    assert not at.exception
    assert any(b.key == 'sector_stock_000001' for b in at.button)
    at.text_input(key='sector_query').set_value('不存在').run()
    at.button(key='sector_group_1').click().run()
    assert not at.exception
    assert at.text_input(key='sector_query').value == ''
