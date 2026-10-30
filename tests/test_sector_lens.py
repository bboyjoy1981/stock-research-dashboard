import pandas as pd
from streamlit.testing.v1 import AppTest


def test_sector_snapshot_keeps_unknown_changes_out_of_breadth():
    from src.sector_lens import sector_snapshot
    frame = pd.DataFrame({'行业': ['电子', '电子', '电子设备', '电子'],
                          '涨跌幅': [3, -1, 10, None], '成交额': [200, 100, 999, None]})
    result = sector_snapshot(frame, '行业', '电子')
    assert result['rows'] == 3
    assert result['valid'] == 2
    assert result['up'] == 1
    assert result['down'] == 1
    assert result['mean'] == 1
    assert result['amount'] == 300


def test_sector_snapshot_missing_data_does_not_invent_zero_change_or_turnover():
    from src.sector_lens import sector_snapshot
    result = sector_snapshot(pd.DataFrame({'行业': ['电子'], '涨跌幅': [None]}), '行业', '电子')
    assert result['mean'] is None
    assert result['amount'] is None
    assert result['valid'] == 0


SCRIPT = '''
import pandas as pd
from src.sector_lens import render_sector_lens
stocks = pd.DataFrame({'代码':['600001','600002','600003'], '名称':['甲','乙','丙'],
                       '行业':['电子','电子','银行'], '涨跌幅':[3,-1,8],
                       '成交额':[200,100,900]})
render_sector_lens(stocks, '行业', {'import_date':'2026-09-16','stock_quote_source':'imported'}, 'test')
'''


def test_sector_board_switches_exact_members_and_opens_stock_with_source():
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    app.selectbox(key='test_sector').set_value('电子').run()
    tables = [item.value for item in app.dataframe]
    assert all('600003' not in table['代码'].tolist() for table in tables)
    assert tables[0]['代码'].tolist() == ['600001']
    assert tables[1]['代码'].tolist() == ['600002']
    app.selectbox(key='test_member').set_value('600002 · 乙').run()
    app.button(key='test_open_stock').click().run()
    assert app.session_state['stock_detail_query'] == '600002'
    assert app.session_state['research_context']['source'] == '行业研究台'
    assert app.session_state['research_context']['industry'] == '电子'


def test_sector_cloud_jump_clears_old_filters_and_sets_exact_scope():
    app = AppTest.from_string(SCRIPT)
    app.session_state['terminal_industry_query'] = '银行'
    app.session_state['core_cloud_parent'] = '旧分类'
    app.run()
    app.selectbox(key='test_sector').set_value('电子').run()
    app.button(key='test_open_cloud').click().run()
    assert app.session_state['active_nav'] == '大盘云图'
    assert app.session_state['terminal_industry_query'] == ''
    assert app.session_state['core_cloud_parent'] == '全部'
    assert app.session_state['core_cloud_group'] == '电子'
    assert app.session_state['terminal_level'] == '行业'


def test_detail_opens_selected_stocks_actual_industry_cloud():
    from pathlib import Path
    from src.importers import load_research_history, latest_quote_snapshot
    frame, _ = latest_quote_snapshot(load_research_history(str(Path(__file__).resolve().parents[1] / 'data' / 'imports')))
    selected = frame.loc[frame['代码'].astype(str).eq('688008')].iloc[0]
    expected = selected['细分行业']
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py')
    app.session_state['active_nav'] = '个股详情'
    app.session_state['stock_detail_query'] = '688008'
    app.run(timeout=30)
    app.button(key='detail_industry_cloud').click().run(timeout=30)
    assert not app.exception
    assert app.session_state['active_nav'] == '大盘云图'
    assert app.selectbox(key='core_cloud_group').value == expected


def test_sector_blank_classification_is_consistent_with_selector():
    from src.sector_lens import sector_snapshot
    result = sector_snapshot(pd.DataFrame({'行业': ['', None], '涨跌幅': [1, -1]}), '行业', '未分类')
    assert result['rows'] == 2


def test_sector_jump_retains_unique_parent_of_same_named_child():
    app = AppTest.from_string('''
import pandas as pd
from src.sector_lens import render_sector_lens
stocks=pd.DataFrame({'代码':['1','2'], '名称':['甲','乙'], '行业':['电子','电子'],
                     '细分行业':['半导体','半导体'], '涨跌幅':[1,-1]})
render_sector_lens(stocks,'细分行业',{},'parent')
''').run()
    app.button(key='parent_open_cloud').click().run()
    assert app.session_state['core_cloud_parent'] == '电子'
    assert app.session_state['core_cloud_group'] == '半导体'
