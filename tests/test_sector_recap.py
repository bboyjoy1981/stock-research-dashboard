import pandas as pd
from streamlit.testing.v1 import AppTest


def test_recap_counts_unknown_separately_and_uses_real_positive_turnover():
    from src.sector_lens import sector_recap
    result = sector_recap(pd.DataFrame({'涨跌幅': [-6, -3, 0, 2, 6, None],
                                       '成交额': [10, 20, 30, 40, 100, None]}))
    assert result['distribution']['家数'].tolist() == [1, 1, 0, 1, 1, 0, 1, 1]
    assert result['top3_share'] == .85
    assert result['positive_amount_count'] == 5


def test_recap_missing_or_zero_turnover_has_no_fabricated_concentration():
    from src.sector_lens import sector_recap
    result = sector_recap(pd.DataFrame({'涨跌幅':[None], '成交额':[0]}))
    assert result['top3_share'] is None
    assert result['distribution']['家数'].sum() == 1


def test_same_named_children_can_be_researched_in_exact_parent_scope():
    app = AppTest.from_string('''
import pandas as pd
from src.sector_lens import render_sector_lens
stocks=pd.DataFrame({'代码':['1','2','3'], '名称':['甲','乙','丙'],
                     '行业':['电子','通信','电子'], '细分行业':['半导体','半导体','元件'],
                     '涨跌幅':[1,-1,2], '成交额':[10,20,30]})
render_sector_lens(stocks,'细分行业',{},'recap')
''').run()
    assert not app.exception
    app.selectbox(key='recap_parent').set_value('电子').run()
    app.selectbox(key='recap_sector').set_value('半导体').run()
    assert app.selectbox(key='recap_member').options == ['1 · 甲']
    app.button(key='recap_open_cloud').click().run()
    assert app.session_state['core_cloud_parent'] == '电子'
    assert app.session_state['core_cloud_group'] == '半导体'
