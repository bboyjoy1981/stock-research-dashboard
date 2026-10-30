import pandas as pd
from streamlit.testing.v1 import AppTest

def test_common_scope_comparison_not_hardcoded_missing():
    app=AppTest.from_string('''
import pandas as pd
from src.market_activity import render_market_activity
render_market_activity({'import_date':'2026-10-13','stocks':pd.DataFrame({'代码':['600000','600001'],'成交额':[150,999],'成交量':[200,999],'成交量单位':['股','股']}),'market_history':pd.DataFrame({'快照日期':['2026-10-12'],'代码':['600000'],'成交额':[100],'成交量':[100],'成交量单位':['股']})})
''').run(timeout=10)
    assert not app.exception
    assert '+50.0%' in app.metric[0].delta
    assert any('共同有效股票' in row.value for row in app.caption)

def test_latest_temperature_reference_not_on_headline(tmp_path):
    app=AppTest.from_string(f'''
from src.market_temperature import _render_temperature_headline
_render_temperature_headline({{'label':'暂无法判断','internal_score':None}},{{}},latest_data={{'temperature_directory':{str(tmp_path)!r}}})
''').run(timeout=10)
    assert not app.exception
    assert [m.label for m in app.metric]==['市场温度']

def test_missing_one_volume_unit_prevents_comparison():
    from src.market_activity import activity_comparison
    data={'import_date':'2026-10-13','stocks':pd.DataFrame({'代码':['a','b'],'成交量':[200,300],'成交量单位':['股',None]}),'market_history':pd.DataFrame({'快照日期':['2026-10-12','2026-10-12'],'代码':['a','b'],'成交量':[100,100],'成交量单位':['股','股']})}
    text,note=activity_comparison(data,'成交量')
    assert '单位未确认' in text and note is None
