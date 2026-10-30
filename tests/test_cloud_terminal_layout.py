from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_cloud_three_workspaces_keep_map_research_and_audit_separate():
    app = AppTest.from_file(APP)
    app.session_state['active_nav'] = '大盘云图'
    app.run(timeout=30)
    assert not app.exception
    tabs = {item.label:item for item in app.tabs}
    assert {'全市场云图','行业研究','导出核对'}.issubset(tabs)
    assert tabs['全市场云图'].get('plotly_chart')
    assert tabs['行业研究'].selectbox(key='cloud_lens_sector').options
    assert any(item.value == '地图范围与覆盖核对' for item in tabs['导出核对'].subheader)
    assert app.session_state['cloud_workspace'] == '全市场云图'


def test_cloud_audit_separates_invalid_quotes_area_and_density_sampling():
    from src.cloud_scope import cloud_scope_audit
    stocks = pd.DataFrame({'涨跌幅':[1,None,-2,0], '成交额':[100,50,0,10]})
    result = cloud_scope_audit(stocks, '成交额', displayed_count=1)
    assert result == {'范围样本':4,'有效涨跌':3,'未知涨跌':1,'可绘制样本':2,'面积无效':1,'实际显示':1,'抽样未显示':1}


def test_equal_weight_cloud_audit_does_not_require_amount():
    from src.cloud_scope import cloud_scope_audit
    result = cloud_scope_audit(pd.DataFrame({'涨跌幅':[1,None]}), '等权', displayed_count=1)
    assert result['可绘制样本'] == 1
    assert result['面积无效'] == 0
