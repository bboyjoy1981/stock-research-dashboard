import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

DAY = '2026-10-09'
NOW = datetime(2026, 10, 9, 16, tzinfo=ZoneInfo('Asia/Shanghai'))

def payload(pool):
    return {'rc':0,'data':{'qdate':20261009,'tc':len(pool),'pool':pool}}

def test_close_pool_keeps_actual_members_and_provider_scope():
    from src.close_limits import build_close_snapshot
    result = build_close_snapshot(payload([{'c':'002058','n':'示例','p':11000,'zdp':9.99}]), payload([]), DAY, NOW)
    assert result['up'][0]['代码'] == '002058'
    assert result['up'][0]['价格'] == 11
    assert result['down'] == []
    assert result['date'] == DAY
    assert 'ST' in result['scope'] and '科创板' in result['scope']

@pytest.mark.parametrize('bad', [None, {'rc':1,'data':None}, {'rc':0,'data':{'qdate':20261008,'tc':0,'pool':[]}}, {'rc':0,'data':{'qdate':20261009,'tc':1,'pool':[]}}])
def test_missing_stale_or_truncated_pool_is_not_zero(bad):
    from src.close_limits import build_close_snapshot
    with pytest.raises(ValueError):
        build_close_snapshot(bad, payload([]), DAY, NOW)

def test_before_close_is_rejected():
    from src.close_limits import build_close_snapshot
    with pytest.raises(ValueError):
        build_close_snapshot(payload([]), payload([]), DAY, NOW.replace(hour=14))

def test_duplicate_members_are_rejected():
    from src.close_limits import build_close_snapshot
    row={'c':'002058','n':'示例','p':11000,'zdp':9.99}
    with pytest.raises(ValueError):
        build_close_snapshot(payload([row,row]),payload([]),DAY,NOW)

def test_saved_snapshot_does_not_leak_into_other_date(tmp_path):
    from src.close_limits import build_close_snapshot,save_close_snapshot,load_close_snapshot
    snapshot=build_close_snapshot(payload([]),payload([]),DAY,NOW)
    save_close_snapshot(tmp_path,snapshot)
    assert load_close_snapshot(tmp_path,DAY)['up']==[]
    assert load_close_snapshot(tmp_path,'2026-10-08') is None

def test_ui_distinguishes_real_zero_and_missing():
    from streamlit.testing.v1 import AppTest
    script="""import pandas as pd
from src.close_limits import render_close_limit_metric
render_close_limit_metric(pd.DataFrame(), '2026-10-09', SNAPSHOT)
"""
    at=AppTest.from_string(script.replace('SNAPSHOT',"{'date':'2026-10-09','up':[],'down':[],'scope':'不含ST、科创板；北交所未确认','source':'https://quote.eastmoney.com/ztb/','captured_at':'2026-10-09T16:00:00+08:00'}")).run(timeout=15)
    assert not at.exception
    assert at.metric[0].value=='0 / 0'
    assert '来源口径' in at.metric[0].label
    at=AppTest.from_string(script.replace('SNAPSHOT','None')).run(timeout=15)
    assert not at.exception
    assert at.metric[0].value=='待补数据'
