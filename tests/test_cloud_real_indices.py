from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_full_cloud_uses_dated_index_snapshot_not_demo_prices(monkeypatch):
    import pandas as pd
    import src.index_snapshot
    # Controlled source boundary: importing newer real quotes must not break this test.
    def dated_snapshot(directory, trade_date):
        return pd.DataFrame([{'名称':'上证指数','价格':3842.19,'涨跌幅':0.31,
                              '交易日期':trade_date,'来源':'测试真实行情边界'}])
    monkeypatch.setattr(src.index_snapshot, 'load_index_snapshot', dated_snapshot)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py')
    app.session_state['active_nav'] = '大盘云图'
    app.run(timeout=30)
    assert not app.exception
    assert '核心指数（演示数据）' not in [item.value for item in app.subheader]
    tables = [item.value for item in app.dataframe if {'名称','点位','涨跌幅'}.issubset(item.value.columns)]
    assert tables
    quote = tables[-1].set_index('名称')
    assert quote.loc['上证指数','点位'] == 3842.19
    assert '北证50' not in quote.index
