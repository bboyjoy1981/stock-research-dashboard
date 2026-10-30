import pandas as pd


def test_activity_requires_comparable_units_and_previous_date():
    from src.market_activity import activity_totals
    data = {'stocks': pd.DataFrame({'成交额': [100, None], '成交量': [20, 30]})}
    result = activity_totals(data)
    assert result['成交额'] == (100, 1, 2)
    assert result['成交量'] == (50, 2, 2)


def test_amount_display_is_readable_and_missing_reference_is_explicit():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string("""
import pandas as pd
from src.market_activity import render_market_activity
render_market_activity({'stocks': pd.DataFrame({'成交额': [1437807000000], '成交量': [90000000000]})})
""").run()
    assert not app.exception
    assert any(item.value == '1.44 万亿元' for item in app.metric)
    assert len(app.metric) == 1
    assert any('成交量：单位待核实' in item.value for item in app.caption)
    assert any(item.label == '当日市场成交额' and item.delta == '较上日：缺上日数据' for item in app.metric)
    assert not any(item.value == '90,000,000,000' for item in app.metric)
    assert any(item.label == '成交统计口径与数据覆盖' for item in app.expander)


def test_ths_total_hands_retains_explicit_volume_unit():
    from src.importers import read_tabular_upload
    raw = '.\t代码\t名称\t.\t总手\n1\tSH600000\t浦发银行\t10万'.encode('gb18030')
    frame = read_tabular_upload(raw, 'Table.txt')
    assert frame.iloc[0]['成交量'] == 100000
    assert frame.iloc[0]['成交量源字段'] == '总手'


def test_confirmed_hands_are_readable_without_inventing_yesterday():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import pandas as pd
from src.market_activity import render_market_activity
render_market_activity({'stocks': pd.DataFrame({'成交量': [100000000, 200000000], '成交量单位':['手','手']})})
''').run()
    assert not app.exception
    assert any('成交量：3.00 亿手' in item.value for item in app.caption)
    assert len(app.metric) == 1


def test_share_unit_does_not_get_displayed_as_hands():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import pandas as pd
from src.market_activity import render_market_activity
render_market_activity({'stocks':pd.DataFrame({'成交量':[300000000], '成交量单位':['股']})})
''').run()
    assert any('成交量：3.00 亿股' in item.value for item in app.caption)
    assert not any('亿手' in item.value for item in app.caption)
