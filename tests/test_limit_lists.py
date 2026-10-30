import pandas as pd
from streamlit.testing.v1 import AppTest


def test_limit_lists_only_include_confirmed_close_limits():
    from src.price_limits import confirmed_limit_rows
    frame = pd.DataFrame({'代码':['600001','300001','600002'], '价格':[11,11,9],
                          '涨停价':[11,12,None], '跌停价':[9,8,None]})
    result = confirmed_limit_rows(frame)
    assert result.loc[result['收盘涨停'], '代码'].tolist() == ['600001']
    assert not result['收盘跌停'].any()


def test_limit_list_missing_data_is_not_empty_market_claim():
    app = AppTest.from_string('''
import pandas as pd
from src.limit_lists import render_limit_lists
render_limit_lists(pd.DataFrame({'代码':['600001'],'价格':[11]}), '2026-09-30')
''').run()
    assert not app.exception
    assert any('缺少实际涨跌停价' in item.value for item in app.info)
    assert not app.dataframe


def test_limit_list_displays_members_and_opens_detail():
    app = AppTest.from_string('''
import pandas as pd
from src.limit_lists import render_limit_lists
render_limit_lists(pd.DataFrame({'代码':['600001'],'名称':['测试股'],'价格':[11],
 '涨跌幅':[10],'涨停价':[11],'跌停价':[9],'细分行业':['PCB']}), '2026-09-30')
''').run()
    assert not app.exception
    assert app.dataframe[0].value['代码'].tolist() == ['600001']
    app.button(key='limits_open_stock').click().run()
    assert app.session_state['active_nav'] == '个股详情'
    assert app.session_state['stock_detail_query'] == '600001'
